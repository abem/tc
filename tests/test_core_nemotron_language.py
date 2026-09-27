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
from types import SimpleNamespace

import pytest
import torch


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


class TestStreamingLanguagePropagation:
    """streaming経路(tc-ops #546 Phase2)が明示的な言語指定を無視する欠落の
    回帰テスト(査sa是正指摘、2026-09-27、2回)。

    **1回目の是正(不十分だった)**: 当初の実装は`main()`で解決済みの
    `language_arg`を`_run_streaming_inference()`/`_build_streaming_chunk_generator()`
    へ渡しておらず、streaming経路のみ`--language`明示指定時でも常に
    Nemotronの既定値"auto"に落ちていた。`language`を各チャンクの
    `processor(...)`呼び出しへ渡すよう是正したが、これだけでは不十分だった。

    **2回目の是正(真因)**: `processor(...)`が`language`から計算するのは
    `inputs["prompt_ids"]`(音声非依存、languageのみで決まる値)だが、
    ストリーミング生成の実際のエントリポイントはこの値を暗黙に参照せず、
    `Nemotron3_5AsrGenerationMixin.generate()`が`model.generate()`呼び出し時の
    **トップレベルkwargs**から`prompt_ids`を取り出す経路のみが有効
    (`processing_nemotron3_5_asr.py`・`generation_nemotron3_5_asr.py`で実ソース
    確認済み)。オフラインバッチ経路は`model.generate(**inputs, ...)`の`**inputs`
    展開で`prompt_ids`キーが自動的にトップレベルへ渡るため意識せず正しく
    動作していたが、streaming経路は`processor(...)`の戻り値から`prompt_ids`を
    一切抽出・転送していなかった。本テストは、`model.generate()`が実際に
    受け取る`prompt_ids`(language文字列→プロンプトID整数への変換結果)を検証する
    (`processor(...)`にlanguageが渡ることの確認だけでは、この真因を検出できない)。
    """

    SAMPLE_AUDIO = str(Path(__file__).parent.parent / "samples" / "e2e_sample.wav")

    # DEFAULT_PROMPT_DICTIONARY(processing_nemotron3_5_asr.py)の実値と一致させた
    # フェイク辞書の抜粋(本テストで使う3言語分のみ)。
    _FAKE_PROMPT_DICTIONARY = {"en-US": 0, "ja-JP": 10, "auto": 101}

    def _make_fake_processor_and_model(self, processor_calls: list, generate_calls: list):
        """processor(...)/model.generate(...)呼び出しに渡されたkwargsをそれぞれ
        記録するフェイクを構築する。実transformers/torchのモデルロード・推論は
        一切発生させない。"""
        frames = 4

        def fake_processor_call(chunk_audio, **kwargs):
            processor_calls.append(kwargs)
            return {"input_features": torch.zeros(1, frames, 80)}

        def fake_resolve_prompt_ids(language, batch_size):
            # 実装(_resolve_prompt_ids)と同じ契約: languageは単一文字列、
            # batch_size件に展開してprompt_dictionaryで整数化する。
            return torch.tensor([self._FAKE_PROMPT_DICTIONARY[language]] * batch_size, dtype=torch.long)

        fake_processor = SimpleNamespace(
            feature_extractor=SimpleNamespace(sampling_rate=16000),
            num_samples_first_audio_chunk=16000,
            num_samples_per_audio_chunk=16000,
            num_mel_frames_first_audio_chunk=frames,
            num_mel_frames_per_audio_chunk=frames,
            set_num_lookahead_tokens=lambda n: None,
            decode=lambda sequences, skip_special_tokens=True: "ダミーの書き起こし結果",
            _resolve_prompt_ids=fake_resolve_prompt_ids,
        )
        # SimpleNamespaceは__call__を通常の属性として持てない(型でなくインスタンスに
        # 生えるため呼び出し不可)ので、呼び出し可能なラッパーで包む
        # (fake_processor(...) がfake_processor_call(...)へ委譲する)。
        fake_processor = _CallableNamespace(fake_processor, fake_processor_call)

        def fake_generate(**kwargs):
            generate_calls.append(kwargs)
            # 実際のtransformers.generate()はgeneratorを内部で逐次消費するが、
            # フェイクではlanguage伝播の検証のため明示的に消費する
            # (processor(...)呼び出しを実際に発火させる)。
            list(kwargs["input_features"])
            return SimpleNamespace(sequences=torch.tensor([[1, 2, 3]]))

        fake_model = SimpleNamespace(generate=fake_generate, device="cpu")
        return fake_processor, fake_model

    def test_explicit_language_reaches_generate_as_prompt_ids(
        self, nemotron_infer_module, monkeypatch
    ):
        """`--language ja-JP`等の明示指定が、streaming経路の`model.generate()`
        呼び出しへ正しいプロンプトID(`prompt_ids`)として実際に伝播すること
        (真因の検証。単に`processor(...)`へ`language`が渡るだけでは不十分)。"""
        processor_calls, generate_calls = [], []
        fake_processor, fake_model = self._make_fake_processor_and_model(processor_calls, generate_calls)

        # transformers.audio_utils.load_audioは生産用.venvでも利用可能(実測確認済み)
        # のため、実ファイル(1秒のサンプル音声)をそのまま読み込ませる。
        result = nemotron_infer_module._run_streaming_inference(
            fake_processor, fake_model, self.SAMPLE_AUDIO, 13, "ja-JP",
        )

        assert len(generate_calls) == 1
        assert "prompt_ids" in generate_calls[0]
        assert generate_calls[0]["prompt_ids"].tolist() == [self._FAKE_PROMPT_DICTIONARY["ja-JP"]]
        assert result["transcription"] == "ダミーの書き起こし結果"

    def test_different_languages_resolve_to_different_prompt_ids(
        self, nemotron_infer_module, monkeypatch
    ):
        """"auto"と明示的な言語("en-US")とで、`model.generate()`が受け取る
        `prompt_ids`が実際に異なる値になること(査sa指摘: 異なる言語条件付け
        トークンにもかかわらず出力が完全一致した=真因が伝播していない証拠、
        という推論を裏付けるための直接的な回帰テスト)。"""
        results = {}
        for language in ("auto", "en-US"):
            processor_calls, generate_calls = [], []
            fake_processor, fake_model = self._make_fake_processor_and_model(processor_calls, generate_calls)
            nemotron_infer_module._run_streaming_inference(
                fake_processor, fake_model, self.SAMPLE_AUDIO, 13, language,
            )
            results[language] = generate_calls[0]["prompt_ids"].tolist()

        assert results["auto"] == [self._FAKE_PROMPT_DICTIONARY["auto"]]
        assert results["en-US"] == [self._FAKE_PROMPT_DICTIONARY["en-US"]]
        assert results["auto"] != results["en-US"]


class _CallableNamespace:
    """SimpleNamespaceの属性群を保持しつつ、インスタンス自体を呼び出し可能にする
    薄いラッパー(`fake_processor(chunk_audio, **kwargs)`の呼び出し形を再現するため)。
    """

    def __init__(self, namespace: SimpleNamespace, call_fn):
        self._namespace = namespace
        self._call_fn = call_fn

    def __call__(self, *args, **kwargs):
        return self._call_fn(*args, **kwargs)

    def __getattr__(self, name):
        return getattr(self._namespace, name)
