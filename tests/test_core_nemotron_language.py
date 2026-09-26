"""
Nemotron 言語自動判定・デバイス指定の回帰テスト(tc-ops #546、2026-09-26緊急是正)。

## 背景(本番不具合)

WebUIでNemotronを選び「自動判定」(既定値)のまま変換すると、以下で必ず失敗していた:

```
文字起こしに失敗しました: Nemotronサブプロセスが異常終了しました(code=1):
ERROR: TypeError: object of type 'NoneType' has no len()
```

**根本原因(査sa確定・作saku裏取り確認済み)**: 旧`scripts/nemotron_infer.py`が
`--language auto`を独自にPython`None`へ変換してから`processor(..., language=None)`
を呼んでいた。`transformers==5.17.0`の実ソース
(`transformers/models/nemotron3_5_asr/processing_nemotron3_5_asr.py`
`_resolve_prompt_ids()`)を直接確認したところ、`isinstance(language, str)`で
文字列判定しており、`None`だと`len(None)`に到達して上記TypeErrorになる
(本番エラーと文言完全一致)。`DEFAULT_PROMPT_DICTIONARY`には`"auto": 101`が
実在し、`__call__()`の`language`引数の既定値も文字列`"auto"`であるため、
**文字列"auto"をそのまま渡すのが正しい**。

本ファイルは、この独自None変換を二度と再導入しないことを保証する回帰テストと、
あわせて是正した`--device`指定(cpu指定が無視されていた疑いの是正)の
単体テストをまとめる。いずれもモデルダウンロード・GPU実行は発生させない
(`resolve_processor_language`/`resolve_device_map`という独立関数の入出力のみを検証する)。
"""
import importlib.util
from pathlib import Path

import pytest


def _load_nemotron_infer_module():
    """scripts/nemotron_infer.py をモジュールとして読み込む。

    このスクリプトはtorch/transformersのimportをmain()内のtry節に遅延させて
    いるため(隔離venv専用の重い依存)、生産用.venv(transformers==4.57.6、
    Nemotronが要求する>=5.13.0とは非互換)からでもモジュールとしてのimport自体は
    安全に行える。`resolve_processor_language`/`resolve_device_map`はモジュール
    トップレベルの純粋関数であり、この読み込みだけで呼び出せる。
    """
    path = Path(__file__).parent.parent / "scripts" / "nemotron_infer.py"
    spec = importlib.util.spec_from_file_location("nemotron_infer_under_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def nemotron_infer_module():
    return _load_nemotron_infer_module()


class TestResolveProcessorLanguage:
    """言語自動判定の回帰テスト(旧不具合の再発防止が主目的)。"""

    def test_auto_stays_string_auto_not_none(self, nemotron_infer_module):
        """最重要回帰: "auto"がNoneへ変換されないこと(旧不具合そのもの)。"""
        result = nemotron_infer_module.resolve_processor_language("auto")
        assert result == "auto"
        assert result is not None

    def test_explicit_language_passthrough(self, nemotron_infer_module):
        """明示的な言語指定(ja-JP等)はそのまま渡されること(既存の成功経路の保護)。"""
        assert nemotron_infer_module.resolve_processor_language("ja-JP") == "ja-JP"
        assert nemotron_infer_module.resolve_processor_language("en-US") == "en-US"

    def test_result_is_always_str_type(self, nemotron_infer_module):
        """戻り値が常にstr型であること(processor内部のisinstance(language, str)
        分岐がFalseになる=len(None)に到達する、という不具合の型レベルでの防止)。"""
        for value in ["auto", "ja-JP", "en-US"]:
            assert isinstance(nemotron_infer_module.resolve_processor_language(value), str)


class TestResolveDeviceMap:
    """デバイス指定無視バグの回帰テスト。

    実運用比較(変換履歴#70: device=cpu指定で327秒音声を33.2秒処理、#71: GPU実行で
    19.5秒。cpu指定時の処理時間がGPU実行と同水準で、cpu指定が無視されていた疑いが
    濃厚)を受けた是正。旧実装はdevice_map="auto"に固定されており、cpu指定を
    反映する経路自体が存在しなかった。"""

    def test_cpu_resolves_to_cpu_device_map(self, nemotron_infer_module):
        """最重要回帰: --device cpu指定時、device_mapがAccelerateの自動配置
        ("auto")ではなく明示的に"cpu"へ解決されること。"""
        assert nemotron_infer_module.resolve_device_map("cpu") == "cpu"

    def test_cuda_resolves_to_cuda_device_map(self, nemotron_infer_module):
        assert nemotron_infer_module.resolve_device_map("cuda") == "cuda"

    def test_auto_resolves_to_auto_device_map(self, nemotron_infer_module):
        assert nemotron_infer_module.resolve_device_map("auto") == "auto"

    def test_unknown_value_falls_back_to_auto(self, nemotron_infer_module):
        """未知の値は安全側(auto)へフォールバックすること。"""
        assert nemotron_infer_module.resolve_device_map("unknown-device") == "auto"
        assert nemotron_infer_module.resolve_device_map("") == "auto"
        assert nemotron_infer_module.resolve_device_map(None) == "auto"


class TestNemotronEngineDeviceArgPassthrough:
    """core/nemotron_engine.py側: TranscriptionConfig.device がサブプロセス呼び出しの
    --device引数へ正しく渡ることの検証(実サブプロセスは起動しない、
    subprocess.runの呼び出し引数のみをモックで検証する)。"""

    def test_device_cpu_is_forwarded_to_subprocess_args(self, monkeypatch):
        from core.config import TranscriptionConfig
        from core.nemotron_engine import NemotronSubprocessEngine
        import core.nemotron_engine as nemotron_engine_module

        captured_args = {}

        class _FakeCompletedProcess:
            returncode = 0
            stdout = (
                '{"chunks": [{"transcription": "", "audio_duration_sec": 1.0, '
                '"infer_elapsed_sec": 0.1}]}'
            )
            stderr = ""

        def _fake_run(args, **kwargs):
            captured_args["args"] = args
            return _FakeCompletedProcess()

        monkeypatch.setattr(nemotron_engine_module.subprocess, "run", _fake_run)
        # 隔離venv未構築チェック(VENV_PYTHON.exists())を通すため、実在するパス
        # (このテストプロセス自身のpython)に差し替える。subprocess.run自体は
        # 上でモック済みのため、実際にこのパスが実行されることはない。
        import sys

        monkeypatch.setattr(nemotron_engine_module, "VENV_PYTHON", Path(sys.executable))

        config = TranscriptionConfig(
            model="nvidia/nemotron-3.5-asr-streaming-0.6b", language="ja", device="cpu"
        )
        engine = NemotronSubprocessEngine(config)
        sample_audio = str(Path(__file__).parent.parent / "samples" / "e2e_sample.wav")
        engine.transcribe(sample_audio)

        args = captured_args["args"]
        assert "--device" in args
        device_idx = args.index("--device")
        assert args[device_idx + 1] == "cpu"
