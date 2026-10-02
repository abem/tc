"""
保存 → アップロード → 履歴記録 → 一時ファイル削除を 1 つにまとめた
core.cli_workflow.finalize_transcription() のテスト(tc-ops #567 Task 5.2)。

実 Drive・実履歴 DB には触れない(upload_transcription_result / record_transcription_history を差し替える)。
"""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from core import cli_workflow
from core.cli_workflow import InputResolution, finalize_transcription
from core.transcription_interface import TranscriptionResult, TranscriptionSegment


def _result(timestamps_included=False):
    return TranscriptionResult(
        text="一行目\n二行目",
        segments=[
            TranscriptionSegment(start=0.0, end=1.0, text="一行目"),
            TranscriptionSegment(start=61.0, end=62.0, text="二行目"),
        ],
        language="ja",
        duration=62.0,
        processing_time=1.0,
        model_name="fake",
        has_speakers=False,
        metadata={"timestamps_included": timestamps_included},
    )


def _resolution(tmp_path, source_type="gdrive", handler=None):
    audio = tmp_path / f"audio_{source_type}.m4a"
    audio.write_bytes(b"x")
    return InputResolution(
        source_type=source_type,
        original_source="https://src.example/x",
        local_audio_path=str(audio),
        is_temp_file=source_type in {"youtube", "twitter"},
        metadata={"title": "t"} if source_type == "youtube" else None,
        youtube_handler=handler,
    )


@pytest.fixture
def mocks(monkeypatch):
    calls = []
    upload = MagicMock(side_effect=lambda **kw: calls.append("upload") or "https://drive.example/u")
    record = MagicMock(side_effect=lambda **kw: calls.append("record"))
    monkeypatch.setattr(cli_workflow, "upload_transcription_result", upload)
    monkeypatch.setattr(cli_workflow, "record_transcription_history", record)
    return type("M", (), {"upload": upload, "record": record, "calls": calls})


SETTINGS = {"device": "cpu"}


def _run(tmp_path, resolution, **kwargs):
    return finalize_transcription(
        result=_result(kwargs.pop("ts", False)),
        resolution=resolution,
        output_dir=tmp_path / "out",
        settings=SETTINGS,
        **kwargs,
    )


def test_full_flow_order_and_outcome(tmp_path, mocks):
    resolution = _resolution(tmp_path, "gdrive")

    outcome = _run(tmp_path, resolution)

    assert mocks.calls == ["upload", "record"]
    assert outcome.gdrive_url == "https://drive.example/u"
    assert outcome.upload_attempted is True
    assert outcome.upload_error is None and outcome.history_error is None and outcome.cleanup_warning is None
    assert outcome.output_file.read_text(encoding="utf-8") == "一行目\n二行目"
    assert not Path(resolution.local_audio_path).exists()
    assert mocks.record.call_args.kwargs["gdrive_url"] == "https://drive.example/u"
    assert mocks.record.call_args.kwargs["output_file"] == outcome.output_file


def test_timestamps_saved_in_mmss_format(tmp_path, mocks):
    outcome = _run(tmp_path, _resolution(tmp_path, "local"), ts=True)

    assert outcome.output_file.read_text(encoding="utf-8") == "[00:00] 一行目\n[01:01] 二行目"


def test_upload_false_skips_upload_but_records_and_cleans(tmp_path, mocks):
    resolution = _resolution(tmp_path, "gdrive")

    outcome = _run(tmp_path, resolution, upload=False)

    mocks.upload.assert_not_called()
    assert outcome.upload_attempted is False and outcome.gdrive_url is None
    mocks.record.assert_called_once()
    assert not Path(resolution.local_audio_path).exists()


@pytest.mark.parametrize("source_type", ["local", "twitter"])
def test_upload_not_attempted_for_local_and_twitter(tmp_path, mocks, source_type):
    outcome = _run(tmp_path, _resolution(tmp_path, source_type))

    mocks.upload.assert_not_called()
    assert outcome.upload_attempted is False


def test_folder_id_is_passed_to_upload(tmp_path, mocks):
    _run(tmp_path, _resolution(tmp_path, "gdrive"), folder_id="F1")

    assert mocks.upload.call_args.kwargs["folder_id"] == "F1"


def test_upload_returning_none_is_recorded_as_attempted_without_url(tmp_path, mocks):
    mocks.upload.side_effect = lambda **kw: None

    outcome = _run(tmp_path, _resolution(tmp_path, "youtube"))

    assert outcome.upload_attempted is True and outcome.gdrive_url is None
    assert mocks.record.call_args.kwargs["gdrive_url"] is None


def test_upload_error_is_captured_by_default_and_flow_continues(tmp_path, mocks):
    mocks.upload.side_effect = RuntimeError("quota")
    resolution = _resolution(tmp_path, "gdrive")

    outcome = _run(tmp_path, resolution)

    assert isinstance(outcome.upload_error, RuntimeError)
    assert outcome.gdrive_url is None
    mocks.record.assert_called_once()
    assert not Path(resolution.local_audio_path).exists()


def test_upload_error_propagates_when_requested_but_still_cleans_up(tmp_path, mocks):
    mocks.upload.side_effect = OSError("drive down")
    resolution = _resolution(tmp_path, "gdrive")

    with pytest.raises(OSError, match="drive down"):
        _run(tmp_path, resolution, raise_upload_errors=True)

    mocks.record.assert_not_called()
    assert not Path(resolution.local_audio_path).exists()


def test_history_error_is_captured_and_cleanup_still_runs(tmp_path, mocks):
    mocks.record.side_effect = RuntimeError("db locked")
    resolution = _resolution(tmp_path, "gdrive")

    outcome = _run(tmp_path, resolution)

    assert isinstance(outcome.history_error, RuntimeError)
    assert outcome.gdrive_url == "https://drive.example/u"
    assert not Path(resolution.local_audio_path).exists()


def test_settings_may_be_a_callable_evaluated_inside_history_step(tmp_path, mocks):
    def broken():
        raise ValueError("bad settings")

    outcome = finalize_transcription(
        result=_result(),
        resolution=_resolution(tmp_path, "local"),
        output_dir=tmp_path / "out",
        settings=broken,
    )

    assert isinstance(outcome.history_error, ValueError)
    assert outcome.output_file.exists()


def test_cleanup_warning_is_returned_not_raised(tmp_path, mocks, monkeypatch):
    monkeypatch.setattr("os.remove", MagicMock(side_effect=PermissionError("denied")))

    outcome = _run(tmp_path, _resolution(tmp_path, "gdrive"))

    assert outcome.cleanup_warning and "denied" in outcome.cleanup_warning


def test_youtube_cleanup_goes_through_handler(tmp_path, mocks):
    handler = MagicMock()
    resolution = _resolution(tmp_path, "youtube", handler=handler)

    _run(tmp_path, resolution)

    handler.cleanup_temp_file.assert_called_once_with(resolution.local_audio_path)


def test_save_failure_propagates_and_still_cleans_up(tmp_path, mocks):
    (tmp_path / "out").write_text("file, not dir")
    resolution = _resolution(tmp_path, "gdrive")

    with pytest.raises(OSError):
        _run(tmp_path, resolution)

    mocks.upload.assert_not_called()
    assert not Path(resolution.local_audio_path).exists()


def test_callbacks_fire_in_order(tmp_path, mocks):
    events = []

    _run(
        tmp_path,
        _resolution(tmp_path, "gdrive"),
        on_saved=lambda path: events.append(("saved", path.name.endswith("_transcription.txt"))),
        on_uploading=lambda: events.append("uploading"),
    )

    assert events == [("saved", True), "uploading"]
