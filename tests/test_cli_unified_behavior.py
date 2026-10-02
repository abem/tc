"""
tc と transcribe.py で挙動を揃える(docs/spec/00-project-spec.md の D4・D5。tc-ops #567 Task 5.1)。

- D4: result.metadata["timestamps_included"] が真で segments があるときだけ、
  各セグメント先頭に [MM:SS] を付けて保存する。それ以外は result.text そのまま。
- D5: 処理の終了時(成功・失敗どちらでも)に、yt-dlp 由来の音声と Google Drive から
  ダウンロードした音声(実体は一時ファイル)を削除する。ローカル入力は削除しない。
  削除に失敗しても結果は失敗にしない(警告のみ)。

実モデル・実 Drive・実ネットワークは使わない(差し替える)。
"""

import importlib.util
import sys
from importlib.machinery import SourceFileLoader
from pathlib import Path

import pytest

import transcribe
from core import cli_workflow
from core.cli_workflow import InputResolution
from core.transcription_interface import TranscriptionResult, TranscriptionSegment

TC_PATH = Path(__file__).resolve().parents[1] / "tc"
GDRIVE_URL = "https://drive.google.com/file/d/FILEID123/view"


@pytest.fixture(scope="module")
def tc_module():
    loader = SourceFileLoader("tc_cli_unified_behavior_under_test", str(TC_PATH))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def _result(timestamps_included):
    segments = [
        TranscriptionSegment(start=0.0, end=1.0, text="最初の文。"),
        TranscriptionSegment(start=65.0, end=68.0, text="次の文。"),
    ]
    return TranscriptionResult(
        text="最初の文。\n次の文。",
        segments=segments,
        language="ja",
        duration=70.0,
        processing_time=1.0,
        model_name="fake-model",
        has_speakers=False,
        metadata={"timestamps_included": timestamps_included},
    )


class FakeTranscriber:
    result = None
    error = None

    def __init__(self, config):
        pass

    def transcribe(self, audio_path, progress_callback=None):
        if FakeTranscriber.error is not None:
            raise FakeTranscriber.error
        return FakeTranscriber.result


class FakeYouTubeHandler:
    def __init__(self):
        self.cleaned = []

    def cleanup_temp_file(self, path):
        self.cleaned.append(path)
        Path(path).unlink(missing_ok=True)


@pytest.fixture
def fake_transcriber(monkeypatch):
    FakeTranscriber.result = _result(False)
    FakeTranscriber.error = None
    return FakeTranscriber


def _make_resolution(tmp_path, source_type, *, handler=None):
    audio = tmp_path / f"downloaded_{source_type}.m4a"
    audio.write_bytes(b"audio")
    # resolve_input_audio の実際の返り値に合わせる(gdrive は is_temp_file=False)
    return InputResolution(
        source_type=source_type,
        original_source=GDRIVE_URL if source_type == "gdrive" else str(audio),
        local_audio_path=str(audio),
        is_temp_file=source_type in {"youtube", "twitter"},
        metadata={"title": "t"} if source_type == "youtube" else None,
        youtube_handler=handler,
    )


class CliHarness:
    """tc と transcribe.py を同じ入口(run)で動かす。"""

    def __init__(self, kind, tc_module, tmp_path, monkeypatch):
        self.kind = kind
        self.tc = tc_module
        self.tmp_path = tmp_path
        self.monkeypatch = monkeypatch
        self.resolution = None
        monkeypatch.chdir(tmp_path)
        mod = tc_module if kind == "tc" else transcribe
        monkeypatch.setattr(mod, "UnifiedTranscriber", FakeTranscriber)
        monkeypatch.setattr(mod, "resolve_input_audio", lambda *a, **k: self.resolution)
        monkeypatch.setattr(cli_workflow, "upload_transcription_result", lambda **k: None)
        monkeypatch.setattr(cli_workflow, "record_transcription_history", lambda **k: None)
        if kind == "tc":
            monkeypatch.setattr(
                mod, "load_config", lambda: {"whisper": {"model": "m", "language": "ja", "device": "cpu"}}
            )
        else:
            monkeypatch.setattr(transcribe.UnifiedConfig, "get", classmethod(lambda cls, *a, **k: k.get("default")))

    def run(self):
        if self.kind == "tc":
            monkeypatch_argv = ["tc", "input", "--output-dir", str(self.tmp_path / "output"), "--no-upload"]
            self.monkeypatch.setattr(sys, "argv", monkeypatch_argv)
            self.tc.main()
        else:
            loader = transcribe.TranscribeLoader()
            settings = {"model": "m", "language": "ja", "device": "cpu"}
            loader.process_with_progress({"type": self.resolution.source_type, "source": "input"}, settings)

    def saved_text(self):
        files = sorted((self.tmp_path / "output").glob("*_transcription.txt"))
        assert len(files) == 1
        return files[0].read_text(encoding="utf-8")


@pytest.fixture(params=["tc", "transcribe.py"])
def cli(request, tc_module, tmp_path, monkeypatch, fake_transcriber):
    return CliHarness("tc" if request.param == "tc" else "transcribe", tc_module, tmp_path, monkeypatch)


class TestSaveFormat:
    def test_timestamps_included_saves_mmss_per_line(self, cli, tmp_path):
        FakeTranscriber.result = _result(True)
        cli.resolution = _make_resolution(tmp_path, "local")

        cli.run()

        assert cli.saved_text() == "[00:00] 最初の文。\n[01:05] 次の文。"

    def test_timestamps_not_included_saves_plain_text(self, cli, tmp_path):
        FakeTranscriber.result = _result(False)
        cli.resolution = _make_resolution(tmp_path, "local")

        cli.run()

        assert cli.saved_text() == "最初の文。\n次の文。"


class TestTempFileCleanup:
    def test_gdrive_download_is_removed_after_success(self, cli, tmp_path):
        cli.resolution = _make_resolution(tmp_path, "gdrive")

        cli.run()

        assert not Path(cli.resolution.local_audio_path).exists()

    def test_gdrive_download_is_removed_after_failure(self, cli, tmp_path):
        cli.resolution = _make_resolution(tmp_path, "gdrive")
        FakeTranscriber.error = RuntimeError("boom")

        with pytest.raises(RuntimeError):
            cli.run()

        assert not Path(cli.resolution.local_audio_path).exists()

    def test_youtube_audio_is_cleaned_via_handler_after_success(self, cli, tmp_path):
        handler = FakeYouTubeHandler()
        cli.resolution = _make_resolution(tmp_path, "youtube", handler=handler)

        cli.run()

        assert handler.cleaned == [cli.resolution.local_audio_path]

    def test_youtube_audio_is_cleaned_via_handler_after_failure(self, cli, tmp_path):
        handler = FakeYouTubeHandler()
        cli.resolution = _make_resolution(tmp_path, "youtube", handler=handler)
        FakeTranscriber.error = RuntimeError("boom")

        with pytest.raises(RuntimeError):
            cli.run()

        assert handler.cleaned == [cli.resolution.local_audio_path]

    def test_local_input_is_never_removed(self, cli, tmp_path):
        cli.resolution = _make_resolution(tmp_path, "local")

        cli.run()

        assert Path(cli.resolution.local_audio_path).exists()

    def test_cleanup_failure_does_not_fail_the_run(self, cli, tmp_path, monkeypatch):
        cli.resolution = _make_resolution(tmp_path, "gdrive")

        def failing_remove(path):
            raise PermissionError("nope")

        monkeypatch.setattr("os.remove", failing_remove)

        cli.run()  # 例外を出さない


# ---------------------------------------------------------------- 共通関数の単体
class TestSharedHelpers:
    def test_needs_cleanup_per_source_type(self, tmp_path):
        assert _make_resolution(tmp_path, "gdrive").needs_cleanup is True
        assert _make_resolution(tmp_path, "youtube").needs_cleanup is True
        assert _make_resolution(tmp_path, "twitter").needs_cleanup is True
        assert _make_resolution(tmp_path, "local").needs_cleanup is False

    def test_cleanup_failure_returns_warning_message(self, tmp_path, monkeypatch):
        from core.cli_workflow import cleanup_input_audio

        resolution = _make_resolution(tmp_path, "gdrive")
        monkeypatch.setattr("os.remove", lambda path: (_ for _ in ()).throw(OSError("denied")))

        warning = cleanup_input_audio(resolution)

        assert warning is not None and "denied" in warning

    def test_cleanup_missing_file_is_silent(self, tmp_path):
        from core.cli_workflow import cleanup_input_audio

        resolution = _make_resolution(tmp_path, "gdrive")
        Path(resolution.local_audio_path).unlink()

        assert cleanup_input_audio(resolution) is None
