"""
Nemotron-3.5-ASR-Streaming 追加に伴う回帰テスト(tc-ops #546 Phase2)。

`core/nemotron_engine.py`(NemotronSubprocessEngine)追加により、
`UnifiedTranscriber.__init__` のディスパッチロジックに `is_nemotron_model`
判定を `is_qwen3_model` 判定より前に挿入した。既存3モデル名の解決結果が
変わらないこと(回帰)・Nemotronが新規に正しく解決されること・
両判定関数が文字列として排他的であること(境界値)を検証する。

いずれもモデルダウンロード・GPU実行は発生させない(エンジンクラスの
選択のみを検証する。Phase2設計report §2のテストケース1-5に対応)。
"""

from pathlib import Path

import pytest

SAMPLE_AUDIO = str(Path(__file__).parent.parent / "samples" / "e2e_sample.wav")


def _make_transcriber(model_name: str):
    from core.config import TranscriptionConfig
    from core.transcription_interface import UnifiedTranscriber

    config = TranscriptionConfig(model=model_name, language="ja", device="cpu")
    return UnifiedTranscriber(config)


class TestIsNemotronModel:
    """is_nemotron_model() 単体の判定確認。"""

    def test_nemotron_model_name_detected(self):
        from core.nemotron_engine import is_nemotron_model

        assert is_nemotron_model("nvidia/nemotron-3.5-asr-streaming-0.6b") is True

    def test_case_insensitive(self):
        from core.nemotron_engine import is_nemotron_model

        assert is_nemotron_model("NVIDIA/NEMOTRON-3.5-ASR-STREAMING-0.6B") is True

    @pytest.mark.parametrize(
        "model_name",
        [
            "Qwen/Qwen3-ASR-1.7B",
            "kotoba-tech/kotoba-whisper-v2.2",
            "openai/whisper-large-v3",
            "",
            None,
        ],
    )
    def test_non_nemotron_model_names_not_detected(self, model_name):
        from core.nemotron_engine import is_nemotron_model

        assert is_nemotron_model(model_name) is False


class TestJudgeExclusivity:
    """is_nemotron_model / Qwen3ASREngine.is_qwen3_model の文字列排他性確認
    (Phase2設計report§2: 挿入順序が既存モデル名の解決結果に影響しないことの根拠)。"""

    @pytest.mark.parametrize(
        "model_name",
        [
            "Qwen/Qwen3-ASR-1.7B",
            "kotoba-tech/kotoba-whisper-v2.2",
            "openai/whisper-large-v3",
            "nvidia/nemotron-3.5-asr-streaming-0.6b",
        ],
    )
    def test_at_most_one_judge_is_true(self, model_name):
        from core.nemotron_engine import is_nemotron_model
        from core.transcription_interface import Qwen3ASREngine

        judges = [is_nemotron_model(model_name), Qwen3ASREngine.is_qwen3_model(model_name)]
        assert sum(judges) <= 1, f"{model_name!r} は複数の判定に同時一致してはならない: {judges}"


class TestUnifiedTranscriberDispatch:
    """UnifiedTranscriber.__init__ のエンジン選択結果を検証する
    (既存3モデル名は回帰確認、Nemotronは新規解決の確認)。"""

    def test_qwen3_asr_model_unchanged(self):
        from core.transcription_interface import Qwen3ASREngine

        transcriber = _make_transcriber("Qwen/Qwen3-ASR-1.7B")
        assert isinstance(transcriber.transcription_engine, Qwen3ASREngine)

    def test_kotoba_whisper_model_unchanged(self):
        from core.transcription_interface import WhisperTranscriptionEngine

        transcriber = _make_transcriber("kotoba-tech/kotoba-whisper-v2.2")
        assert isinstance(transcriber.transcription_engine, WhisperTranscriptionEngine)

    def test_openai_whisper_model_unchanged(self):
        from core.transcription_interface import WhisperTranscriptionEngine

        transcriber = _make_transcriber("openai/whisper-large-v3")
        assert isinstance(transcriber.transcription_engine, WhisperTranscriptionEngine)

    def test_nemotron_model_resolves_to_new_engine(self):
        from core.nemotron_engine import NemotronSubprocessEngine

        transcriber = _make_transcriber("nvidia/nemotron-3.5-asr-streaming-0.6b")
        assert isinstance(transcriber.transcription_engine, NemotronSubprocessEngine)


class TestWebuiSelectboxDefaultUnchanged:
    """webui.py のモデルselectbox: Nemotronは末尾追加、index=0(デフォルト)は不変
    (査sa是正指摘反映。作業指示書§3の機械検査と同一観点をpytestでも二重に保証する)。"""

    def test_options_append_default_unchanged(self):
        import ast

        webui_path = Path(__file__).parent.parent / "webui.py"
        tree = ast.parse(webui_path.read_text(encoding="utf-8"))

        found = False
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and getattr(node.func, "attr", None) == "selectbox":
                for kw in node.keywords:
                    if kw.arg == "options" and isinstance(kw.value, ast.List):
                        opts = [e.value for e in kw.value.elts if isinstance(e, ast.Constant)]
                        if opts and "nemotron" in str(opts[-1]).lower() and opts[0] == "Qwen/Qwen3-ASR-1.7B":
                            found = True
        assert found, "モデルselectboxのoptions末尾にnemotronが追加され、index=0のデフォルトが不変であること"


class TestIncludeTimestampsForcedFalseOnNemotron:
    """査sa是正指摘(2026-09-26T14:13): Qwen等でinclude_timestampsをチェック済みの
    状態からNemotronへ切替えると、disabled=Trueだけではウィジェット値がTrueのまま
    保持され、item.settings["include_timestamps"]もTrueで送信されてしまう不具合の
    回帰テスト。streamlit.testing.v1.AppTestで実際のセッション状態遷移(操作順序:
    チェック→Nemotron切替)を再現し、返り値のinclude_timestampsがFalseへ強制される
    ことを検証する(disabled表示の確認だけでは不十分で、値自体の検証が必要)。"""

    HARNESS_PATH = Path(__file__).parent / "fixtures" / "webui_settings_panel_harness.py"

    def test_checked_then_switch_to_nemotron_forces_value_false(self):
        from streamlit.testing.v1 import AppTest

        at = AppTest.from_file(str(self.HARNESS_PATH))
        at.run()
        assert at.exception == []

        # 操作順序の再現: まずQwen3-ASR(デフォルト)のままinclude_timestampsをチェック
        at.checkbox[0].check()
        at.run()
        assert at.session_state["_test_settings"]["include_timestamps"] is True

        # その後Nemotronへ切替える
        at.selectbox[0].select("nvidia/nemotron-3.5-asr-streaming-0.6b")
        at.run()

        settings = at.session_state["_test_settings"]
        assert settings["model"] == "nvidia/nemotron-3.5-asr-streaming-0.6b"
        assert settings["include_timestamps"] is False, (
            "Nemotron選択時はinclude_timestampsの値自体がFalseへ強制されること"
            "(disabled表示だけでは不十分)"
        )
        assert at.checkbox[0].disabled is True


class TestNemotronErrorHandling:
    """隔離venv未構築時のエラーハンドリング設計(Phase2設計report§6)の検証。
    GPU不要・実際のサブプロセス起動は発生させない(venv_pythonパスのみモック)。"""

    def test_missing_venv_raises_runtime_error(self, monkeypatch):
        from core.config import TranscriptionConfig
        from core.nemotron_engine import NemotronSubprocessEngine
        import core.nemotron_engine as nemotron_engine_module

        monkeypatch.setattr(
            nemotron_engine_module, "VENV_PYTHON", Path("/nonexistent/venv-nemotron-poc/bin/python")
        )

        config = TranscriptionConfig(model="nvidia/nemotron-3.5-asr-streaming-0.6b", language="ja", device="cpu")
        engine = NemotronSubprocessEngine(config)

        with pytest.raises(RuntimeError, match="隔離venvが未構築"):
            engine.transcribe(SAMPLE_AUDIO)

    def test_other_engines_unaffected_after_nemotron_error(self, monkeypatch):
        """Nemotronでエラーが起きても、後続の別ジョブ(UnifiedTranscriber新規生成)で
        Qwen3-ASR/Whisperの選択が独立して正常動作することを確認
        (UnifiedTranscriberは呼び出しごとに新規インスタンス化されるため、
        エンジン間の状態共有は構造上発生しない設計であることの検証)。"""
        import core.nemotron_engine as nemotron_engine_module
        from core.transcription_interface import Qwen3ASREngine

        monkeypatch.setattr(
            nemotron_engine_module, "VENV_PYTHON", Path("/nonexistent/venv-nemotron-poc/bin/python")
        )

        nemotron_transcriber = _make_transcriber("nvidia/nemotron-3.5-asr-streaming-0.6b")
        with pytest.raises(RuntimeError):
            nemotron_transcriber.transcription_engine.transcribe(SAMPLE_AUDIO)

        # 別ジョブ相当: 新規UnifiedTranscriberでQwen3-ASRを選択しても正常に解決される
        qwen_transcriber = _make_transcriber("Qwen/Qwen3-ASR-1.7B")
        assert isinstance(qwen_transcriber.transcription_engine, Qwen3ASREngine)
