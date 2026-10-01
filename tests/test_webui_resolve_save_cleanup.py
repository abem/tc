"""
特性テスト(characterization test): tc-ops #567 Task 2.5。

`webui.py` の `_resolve_input()` / `_save_and_record()` / `_cleanup_temp_file()` の現在の挙動を固定する。
後続のリファクタリング(CLI と WebUI の保存処理の共通化)で挙動が変わっていないことを検知するための網。

方針:
- 関数を呼んで、入出力・ファイル副作用・差し替えた関数への引数で検証する(ソース構文の検査はしない)。
- `st.warning` は `webui.st` 経由で差し替え、Streamlit のランタイムは起動しない。
- 実ダウンロード・実 Drive API・実履歴 DB には触れない(`resolve_input_audio` /
  `upload_transcription_result` / `record_transcription_history` は差し替える)。
- `webui.py` は出力先を相対パス `Path("output")` / `Path("output/uploads")` で持つため、
  テスト中は `monkeypatch.chdir(tmp_path)` で実リポジトリの `output/` を汚さない。
"""

import os
import re
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import webui
from core.cli_workflow import InputResolution
from core.transcription_interface import TranscriptionResult, TranscriptionSegment
from core.webui_workflow import TranscriptionJob


# ---------------------------------------------------------------- helpers


@pytest.fixture
def in_tmp_cwd(tmp_path, monkeypatch):
    """相対パスの `output/` を `tmp_path` 配下へ向ける。"""
    monkeypatch.chdir(tmp_path)
    return tmp_path


@pytest.fixture
def warning_mock(monkeypatch):
    mock = MagicMock()
    monkeypatch.setattr(webui.st, "warning", mock)
    return mock


def _resolution(source_type="local", *, local_audio_path="", is_temp_file=False, youtube_handler=None,
                original_source="orig", metadata=None):
    return InputResolution(
        source_type=source_type,
        original_source=original_source,
        local_audio_path=str(local_audio_path),
        is_temp_file=is_temp_file,
        metadata=metadata,
        youtube_handler=youtube_handler,
    )


def _result(text="こんにちは\n世界"):
    return TranscriptionResult(
        text=text,
        segments=[TranscriptionSegment(start=0.0, end=1.5, text="セグメント別テキスト")],
        language="ja",
        duration=1.5,
        processing_time=0.1,
        model_name="dummy-model",
    )


def _job(result):
    job = TranscriptionJob()
    job.result = result
    job.done = True
    return job


class _FakeUpload:
    """Streamlit の UploadedFile の最小代替(`.name` と `.getbuffer()` のみ)。"""

    def __init__(self, name, data):
        self.name = name
        self._data = data

    def getbuffer(self):
        return memoryview(self._data)


# ---------------------------------------------------------------- _resolve_input


class TestResolveInputUrl:
    def test_url_delegates_to_resolve_input_audio_with_expected_args(self, tmp_path, monkeypatch):
        sentinel = _resolution("youtube")
        fake = MagicMock(return_value=sentinel)
        monkeypatch.setattr(webui, "resolve_input_audio", fake)
        on_status = MagicMock()
        download_dir = tmp_path / "dl"

        actual = webui._resolve_input(
            {"source_url": "https://www.youtube.com/watch?v=abc", "uploaded_file": None}, download_dir, on_status
        )

        assert actual is sentinel
        fake.assert_called_once_with(
            "https://www.youtube.com/watch?v=abc", download_dir, ensure_yt_dlp=True, on_status=on_status
        )
        on_status.assert_not_called()  # webui 側は on_status を自分では呼ばない

    def test_url_takes_priority_over_uploaded_file_and_writes_no_upload(self, in_tmp_cwd, monkeypatch):
        sentinel = _resolution("youtube")
        monkeypatch.setattr(webui, "resolve_input_audio", MagicMock(return_value=sentinel))
        upload = _FakeUpload("a.wav", b"data")

        actual = webui._resolve_input(
            {"source_url": "https://youtu.be/x", "uploaded_file": upload}, in_tmp_cwd / "dl", MagicMock()
        )

        assert actual is sentinel
        assert not (in_tmp_cwd / "output").exists()

    def test_on_status_is_forwarded_and_usable_by_resolver(self, tmp_path, monkeypatch):
        """渡した on_status がそのまま resolve_input_audio から呼べる(UI 呼び出しに置き換えられない)。"""

        def _fake(source, output_dir, *, ensure_yt_dlp, on_status):
            on_status("検出しました")
            return _resolution("youtube")

        monkeypatch.setattr(webui, "resolve_input_audio", _fake)
        messages = []

        webui._resolve_input({"source_url": "https://youtu.be/x", "uploaded_file": None}, tmp_path, messages.append)

        assert messages == ["検出しました"]

    def test_url_resolution_failure_is_logged_and_reraised(self, tmp_path, monkeypatch):
        boom = RuntimeError("download failed")
        monkeypatch.setattr(webui, "resolve_input_audio", MagicMock(side_effect=boom))
        logger_mock = MagicMock()
        monkeypatch.setattr(webui, "logger", logger_mock)
        download_dir = tmp_path / "token1234"

        with pytest.raises(RuntimeError, match="download failed"):
            webui._resolve_input({"source_url": "https://youtu.be/x", "uploaded_file": None}, download_dir, MagicMock())

        logger_mock.error.assert_called_once()
        logged_args = logger_mock.error.call_args.args
        assert "token1234" in logged_args  # token は download_dir.name
        assert boom in logged_args

    def test_base_exception_is_not_caught(self, tmp_path, monkeypatch):
        """`except Exception` なので、RerunException のような BaseException 派生はそのまま伝播する。"""

        class _Interrupt(BaseException):
            pass

        logger_mock = MagicMock()
        monkeypatch.setattr(webui, "logger", logger_mock)
        monkeypatch.setattr(webui, "resolve_input_audio", MagicMock(side_effect=_Interrupt()))

        with pytest.raises(_Interrupt):
            webui._resolve_input({"source_url": "https://youtu.be/x", "uploaded_file": None}, tmp_path, MagicMock())

        logger_mock.error.assert_not_called()


class TestResolveInputUploadedFile:
    def test_uploaded_file_is_saved_under_output_uploads_and_resolution_is_local(self, in_tmp_cwd, monkeypatch):
        resolver = MagicMock()
        monkeypatch.setattr(webui, "resolve_input_audio", resolver)
        payload = b"RIFF\x00\x01binary-audio-bytes"

        actual = webui._resolve_input(
            {"source_url": "", "uploaded_file": _FakeUpload("会議 録音.wav", payload)}, in_tmp_cwd / "dl", MagicMock()
        )

        saved = Path("output/uploads/会議 録音.wav")
        assert saved.read_bytes() == payload
        assert (in_tmp_cwd / "output" / "uploads" / "会議 録音.wav").read_bytes() == payload
        assert actual == InputResolution(
            source_type="local",
            original_source=str(saved),
            local_audio_path=str(saved),
            is_temp_file=False,
            metadata=None,
            youtube_handler=None,
        )
        assert actual.original_source == "output/uploads/会議 録音.wav"  # 相対パスのまま
        resolver.assert_not_called()

    def test_download_dir_is_not_used_for_uploaded_file(self, in_tmp_cwd, monkeypatch):
        monkeypatch.setattr(webui, "resolve_input_audio", MagicMock())
        download_dir = in_tmp_cwd / "dl"

        webui._resolve_input({"source_url": "", "uploaded_file": _FakeUpload("a.wav", b"x")}, download_dir, MagicMock())

        assert not download_dir.exists()

    def test_same_filename_upload_overwrites_previous_file(self, in_tmp_cwd, monkeypatch):
        monkeypatch.setattr(webui, "resolve_input_audio", MagicMock())
        form = {"source_url": "", "uploaded_file": _FakeUpload("same.wav", b"first-content")}
        webui._resolve_input(form, in_tmp_cwd, MagicMock())
        form = {"source_url": "", "uploaded_file": _FakeUpload("same.wav", b"2nd")}

        webui._resolve_input(form, in_tmp_cwd, MagicMock())

        assert (in_tmp_cwd / "output" / "uploads" / "same.wav").read_bytes() == b"2nd"
        assert [p.name for p in (in_tmp_cwd / "output" / "uploads").iterdir()] == ["same.wav"]

    def test_empty_uploaded_file_is_saved_as_empty_file(self, in_tmp_cwd, monkeypatch):
        monkeypatch.setattr(webui, "resolve_input_audio", MagicMock())

        actual = webui._resolve_input(
            {"source_url": "", "uploaded_file": _FakeUpload("empty.wav", b"")}, in_tmp_cwd, MagicMock()
        )

        assert actual is not None
        assert (in_tmp_cwd / "output" / "uploads" / "empty.wav").read_bytes() == b""

    def test_none_url_with_uploaded_file_uses_upload_path(self, in_tmp_cwd, monkeypatch):
        """source_url が空文字ではなく None でも、アップロード経路に入る。"""
        resolver = MagicMock()
        monkeypatch.setattr(webui, "resolve_input_audio", resolver)

        actual = webui._resolve_input(
            {"source_url": None, "uploaded_file": _FakeUpload("n.wav", b"n")}, in_tmp_cwd, MagicMock()
        )

        assert actual.source_type == "local"
        resolver.assert_not_called()


class TestResolveInputNothing:
    def test_no_url_and_no_upload_returns_none(self, in_tmp_cwd, monkeypatch):
        resolver = MagicMock()
        monkeypatch.setattr(webui, "resolve_input_audio", resolver)
        on_status = MagicMock()

        actual = webui._resolve_input({"source_url": "", "uploaded_file": None}, in_tmp_cwd / "dl", on_status)

        assert actual is None
        resolver.assert_not_called()
        on_status.assert_not_called()
        assert not (in_tmp_cwd / "output").exists()
        assert not (in_tmp_cwd / "dl").exists()


# ---------------------------------------------------------------- _cleanup_temp_file


class TestCleanupTempFile:
    def test_temp_file_is_removed(self, tmp_path, warning_mock):
        audio = tmp_path / "dl.wav"
        audio.write_bytes(b"x")

        webui._cleanup_temp_file(_resolution("twitter", local_audio_path=audio, is_temp_file=True))

        assert not audio.exists()
        warning_mock.assert_not_called()

    def test_non_temp_local_file_is_kept(self, tmp_path, warning_mock):
        audio = tmp_path / "upload.wav"
        audio.write_bytes(b"x")

        webui._cleanup_temp_file(_resolution("local", local_audio_path=audio, is_temp_file=False))

        assert audio.read_bytes() == b"x"
        warning_mock.assert_not_called()

    def test_non_temp_youtube_resolution_is_kept(self, tmp_path, warning_mock):
        """is_temp_file が偽で source_type も gdrive でなければ、youtube でも削除しない。"""
        audio = tmp_path / "dl.wav"
        audio.write_bytes(b"x")
        handler = MagicMock()

        webui._cleanup_temp_file(
            _resolution("youtube", local_audio_path=audio, is_temp_file=False, youtube_handler=handler)
        )

        assert audio.exists()
        handler.cleanup_temp_file.assert_not_called()

    def test_gdrive_source_is_removed_even_when_is_temp_file_is_false(self, tmp_path, warning_mock):
        """resolve_input_audio は gdrive で is_temp_file=False を返すが、source_type=="gdrive" なら削除する。"""
        audio = tmp_path / "gdrive_dl.wav"
        audio.write_bytes(b"x")

        webui._cleanup_temp_file(_resolution("gdrive", local_audio_path=audio, is_temp_file=False))

        assert not audio.exists()
        warning_mock.assert_not_called()

    def test_missing_file_is_noop_without_warning(self, tmp_path, warning_mock):
        missing = tmp_path / "already_gone.wav"

        webui._cleanup_temp_file(_resolution("youtube", local_audio_path=missing, is_temp_file=True))

        assert not missing.exists()
        warning_mock.assert_not_called()

    def test_youtube_handler_cleanup_is_used_instead_of_os_remove(self, tmp_path, warning_mock):
        audio = tmp_path / "dl.wav"
        audio.write_bytes(b"x")
        handler = MagicMock()

        webui._cleanup_temp_file(
            _resolution("youtube", local_audio_path=audio, is_temp_file=True, youtube_handler=handler)
        )

        handler.cleanup_temp_file.assert_called_once_with(str(audio))
        assert audio.exists()  # ファイル削除はハンドラ(ここではモック)の責務
        warning_mock.assert_not_called()

    def test_youtube_handler_not_called_when_file_is_missing(self, tmp_path, warning_mock):
        handler = MagicMock()

        webui._cleanup_temp_file(
            _resolution("youtube", local_audio_path=tmp_path / "gone.wav", is_temp_file=True, youtube_handler=handler)
        )

        handler.cleanup_temp_file.assert_not_called()

    def test_none_resolution_raises_attribute_error(self, warning_mock):
        """resolution が None のときの現状: 防御されておらず AttributeError が伝播する(st.warning も出ない)。"""
        with pytest.raises(AttributeError):
            webui._cleanup_temp_file(None)  # type: ignore[arg-type]

        warning_mock.assert_not_called()

    def test_os_remove_failure_emits_warning_and_does_not_raise(self, tmp_path, monkeypatch, warning_mock):
        audio = tmp_path / "locked.wav"
        audio.write_bytes(b"x")

        def _boom(path):
            raise PermissionError("denied")

        monkeypatch.setattr(webui.os, "remove", _boom)

        webui._cleanup_temp_file(_resolution("twitter", local_audio_path=audio, is_temp_file=True))

        warning_mock.assert_called_once()
        message = warning_mock.call_args.args[0]
        assert message.startswith("一時ファイルの削除に失敗しました: ")
        assert "denied" in message

    def test_handler_cleanup_failure_emits_warning_and_does_not_raise(self, tmp_path, warning_mock):
        audio = tmp_path / "dl.wav"
        audio.write_bytes(b"x")
        handler = MagicMock()
        handler.cleanup_temp_file.side_effect = OSError("handler broke")

        webui._cleanup_temp_file(
            _resolution("youtube", local_audio_path=audio, is_temp_file=True, youtube_handler=handler)
        )

        warning_mock.assert_called_once()
        assert "handler broke" in warning_mock.call_args.args[0]


# ---------------------------------------------------------------- _save_and_record


@pytest.fixture
def workflow_mocks(monkeypatch):
    """外部 I/O(Drive アップロード・履歴 DB)を差し替える。呼び出し順も記録する。"""
    calls = []
    upload = MagicMock(return_value="https://drive.example/file/1")
    record = MagicMock(return_value=None)
    cleanup = MagicMock()
    upload.side_effect = lambda **kw: calls.append("upload") or "https://drive.example/file/1"
    record.side_effect = lambda **kw: calls.append("record")
    cleanup.side_effect = lambda r: calls.append("cleanup")
    monkeypatch.setattr(webui, "upload_transcription_result", upload)
    monkeypatch.setattr(webui, "record_transcription_history", record)
    monkeypatch.setattr(webui, "_cleanup_temp_file", cleanup)
    return SimpleNamespace(upload=upload, record=record, cleanup=cleanup, calls=calls)


_SETTINGS = {"model": "dummy", "device": "cpu", "language": "ja", "include_timestamps": True}


class TestSaveAndRecordFile:
    def test_text_is_saved_under_output_with_timestamped_name(self, in_tmp_cwd, workflow_mocks, warning_mock):
        text = "こんにちは\n世界 — 日本語の本文"
        resolution = _resolution("local", local_audio_path="a.wav")

        output_file, gdrive_url = webui._save_and_record(_job(_result(text)), resolution, _SETTINGS)

        saved = Path(output_file)
        assert saved.parent == Path("output")
        assert re.fullmatch(r"\d{8}_\d{6}_transcription\.txt", saved.name)
        assert (in_tmp_cwd / saved).read_text(encoding="utf-8") == text
        assert (in_tmp_cwd / saved).read_bytes() == text.encode("utf-8")  # BOM・改行変換なし
        assert gdrive_url is None

    def test_file_content_is_result_text_only_regardless_of_segments_and_timestamp_setting(
        self, in_tmp_cwd, workflow_mocks, warning_mock
    ):
        """保存内容は result.text そのもの。segments(開始/終了時刻)や settings の include_timestamps は
        内容に影響しない(タイムスタンプ付与の有無は `UnifiedTranscriber` が result.text を作る段階で決まる)。"""
        result = _result("本文のみ")
        for include_timestamps in (True, False):
            settings = dict(_SETTINGS, include_timestamps=include_timestamps)
            output_file, _ = webui._save_and_record(_job(result), _resolution("local"), settings)
            assert (in_tmp_cwd / output_file).read_text(encoding="utf-8") == "本文のみ"
            assert "セグメント別テキスト" not in (in_tmp_cwd / output_file).read_text(encoding="utf-8")

    def test_empty_text_creates_empty_file(self, in_tmp_cwd, workflow_mocks, warning_mock):
        output_file, _ = webui._save_and_record(_job(_result("")), _resolution("local"), _SETTINGS)

        assert (in_tmp_cwd / output_file).read_bytes() == b""

    def test_output_dir_is_created_when_missing(self, in_tmp_cwd, workflow_mocks, warning_mock):
        assert not (in_tmp_cwd / "output").exists()

        webui._save_and_record(_job(_result()), _resolution("local"), _SETTINGS)

        assert (in_tmp_cwd / "output").is_dir()

    def test_return_value_is_str_path_and_gdrive_url_tuple(self, in_tmp_cwd, workflow_mocks, warning_mock):
        output_file, gdrive_url = webui._save_and_record(
            _job(_result()), _resolution("youtube", original_source="https://youtu.be/x"), _SETTINGS
        )

        assert isinstance(output_file, str)
        assert gdrive_url == "https://drive.example/file/1"
        assert workflow_mocks.upload.call_args.kwargs["output_file"] == Path(output_file)

    def test_job_without_result_raises_attribute_error_and_leaves_empty_file(
        self, in_tmp_cwd, workflow_mocks, warning_mock
    ):
        """job.result が None のときの現状: `result.text` で AttributeError。ただし open("w") が先に
        実行されるため、空の出力ファイルが残る(アップロード・履歴・一時削除は実行されない)。"""
        job = TranscriptionJob()  # result=None

        with pytest.raises(AttributeError):
            webui._save_and_record(job, _resolution("local"), _SETTINGS)

        leftovers = list((in_tmp_cwd / "output").glob("*_transcription.txt"))
        assert len(leftovers) == 1
        assert leftovers[0].read_bytes() == b""
        workflow_mocks.upload.assert_not_called()
        workflow_mocks.record.assert_not_called()
        workflow_mocks.cleanup.assert_not_called()


class TestSaveAndRecordUploadAndHistory:
    @pytest.mark.parametrize("source_type", ["youtube", "gdrive"])
    def test_upload_called_for_youtube_and_gdrive_with_expected_args(
        self, source_type, in_tmp_cwd, workflow_mocks, warning_mock
    ):
        metadata = {"title": "t", "video_id": "v"}
        resolution = _resolution(source_type, original_source="https://src.example/x", metadata=metadata)

        output_file, gdrive_url = webui._save_and_record(_job(_result()), resolution, _SETTINGS)

        workflow_mocks.upload.assert_called_once_with(
            source_type=source_type,
            original_source="https://src.example/x",
            output_file=Path(output_file),
            metadata=metadata,
        )
        assert gdrive_url == "https://drive.example/file/1"

    @pytest.mark.parametrize("source_type", ["local", "twitter"])
    def test_upload_not_called_for_other_source_types(self, source_type, in_tmp_cwd, workflow_mocks, warning_mock):
        """現状: local に加えて twitter(X動画URL)も Drive アップロード対象外(gdrive_url は None)。"""
        output_file, gdrive_url = webui._save_and_record(_job(_result()), _resolution(source_type), _SETTINGS)

        workflow_mocks.upload.assert_not_called()
        assert gdrive_url is None
        assert (in_tmp_cwd / output_file).exists()

    def test_upload_returning_none_yields_none_url(self, in_tmp_cwd, workflow_mocks, warning_mock):
        workflow_mocks.upload.side_effect = lambda **kw: None

        _, gdrive_url = webui._save_and_record(_job(_result()), _resolution("youtube"), _SETTINGS)

        assert gdrive_url is None
        assert workflow_mocks.record.call_args.kwargs["gdrive_url"] is None

    def test_history_recorded_with_expected_args(self, in_tmp_cwd, workflow_mocks, warning_mock):
        result = _result()
        resolution = _resolution("youtube", original_source="https://youtu.be/x")

        output_file, gdrive_url = webui._save_and_record(_job(result), resolution, _SETTINGS)

        workflow_mocks.record.assert_called_once()
        assert workflow_mocks.record.call_args.args == ()
        kwargs = workflow_mocks.record.call_args.kwargs
        assert set(kwargs) == {"result", "resolution", "output_file", "settings", "gdrive_url"}
        assert kwargs["result"] is result
        assert kwargs["resolution"] is resolution
        assert kwargs["output_file"] == Path(output_file)
        assert isinstance(kwargs["output_file"], Path)
        assert kwargs["settings"] is _SETTINGS
        assert kwargs["gdrive_url"] == gdrive_url == "https://drive.example/file/1"

    def test_history_recorded_for_local_source_with_none_url(self, in_tmp_cwd, workflow_mocks, warning_mock):
        webui._save_and_record(_job(_result()), _resolution("local"), _SETTINGS)

        workflow_mocks.record.assert_called_once()
        assert workflow_mocks.record.call_args.kwargs["gdrive_url"] is None

    def test_cleanup_is_called_with_resolution_and_order_is_upload_record_cleanup(
        self, in_tmp_cwd, workflow_mocks, warning_mock
    ):
        resolution = _resolution("youtube")

        webui._save_and_record(_job(_result()), resolution, _SETTINGS)

        workflow_mocks.cleanup.assert_called_once_with(resolution)
        assert workflow_mocks.calls == ["upload", "record", "cleanup"]
        warning_mock.assert_not_called()


class TestSaveAndRecordFailures:
    def test_upload_failure_warns_and_continues(self, in_tmp_cwd, workflow_mocks, warning_mock):
        """Drive アップロード失敗は例外にならず st.warning。ファイル保存・履歴記録・一時削除は続行される。"""
        workflow_mocks.upload.side_effect = RuntimeError("quota exceeded")

        output_file, gdrive_url = webui._save_and_record(_job(_result("本文")), _resolution("youtube"), _SETTINGS)

        assert gdrive_url is None
        assert (in_tmp_cwd / output_file).read_text(encoding="utf-8") == "本文"
        warning_mock.assert_called_once()
        message = warning_mock.call_args.args[0]
        assert message.startswith("Google Driveアップロードに失敗しました: ")
        assert "quota exceeded" in message
        workflow_mocks.record.assert_called_once()
        assert workflow_mocks.record.call_args.kwargs["gdrive_url"] is None
        workflow_mocks.cleanup.assert_called_once()

    def test_history_failure_warns_and_still_returns_result_and_cleans_up(
        self, in_tmp_cwd, workflow_mocks, warning_mock
    ):
        workflow_mocks.record.side_effect = sqlite_error = RuntimeError("db locked")

        output_file, gdrive_url = webui._save_and_record(_job(_result()), _resolution("youtube"), _SETTINGS)

        assert gdrive_url == "https://drive.example/file/1"
        assert (in_tmp_cwd / output_file).exists()
        warning_mock.assert_called_once()
        message = warning_mock.call_args.args[0]
        assert message.startswith("変換履歴の記録に失敗しました: ")
        assert str(sqlite_error) in message
        workflow_mocks.cleanup.assert_called_once()

    def test_upload_and_history_both_fail_emit_two_warnings_in_order(self, in_tmp_cwd, workflow_mocks, warning_mock):
        workflow_mocks.upload.side_effect = RuntimeError("up")
        workflow_mocks.record.side_effect = RuntimeError("hist")

        webui._save_and_record(_job(_result()), _resolution("gdrive"), _SETTINGS)

        messages = [c.args[0] for c in warning_mock.call_args_list]
        assert len(messages) == 2
        assert messages[0].startswith("Google Driveアップロードに失敗しました")
        assert messages[1].startswith("変換履歴の記録に失敗しました")
        workflow_mocks.cleanup.assert_called_once()

    def test_unwritable_output_dir_propagates_and_skips_upload_record_cleanup(
        self, tmp_path, monkeypatch, workflow_mocks, warning_mock
    ):
        """ファイル保存自体の失敗は握りつぶされず例外が伝播する(アップロード・履歴・削除は実行されない)。"""
        monkeypatch.chdir(tmp_path)
        (tmp_path / "output").write_text("これはディレクトリではなくファイル")  # mkdir/open が失敗する

        with pytest.raises(OSError):
            webui._save_and_record(_job(_result()), _resolution("youtube"), _SETTINGS)

        workflow_mocks.upload.assert_not_called()
        workflow_mocks.record.assert_not_called()
        workflow_mocks.cleanup.assert_not_called()


class TestSaveAndRecordWithRealCleanup:
    """`_cleanup_temp_file` を差し替えない統合寄りの確認: 保存後に一時ファイルが消え、アップロード済み
    ローカルファイルは残る。"""

    def test_temp_download_removed_and_local_upload_kept(self, in_tmp_cwd, monkeypatch, warning_mock):
        monkeypatch.setattr(webui, "upload_transcription_result", MagicMock(return_value=None))
        monkeypatch.setattr(webui, "record_transcription_history", MagicMock())
        temp_audio = in_tmp_cwd / "dl.wav"
        temp_audio.write_bytes(b"x")
        local_audio = in_tmp_cwd / "keep.wav"
        local_audio.write_bytes(b"y")

        webui._save_and_record(
            _job(_result()), _resolution("twitter", local_audio_path=temp_audio, is_temp_file=True), _SETTINGS
        )
        webui._save_and_record(_job(_result()), _resolution("local", local_audio_path=local_audio), _SETTINGS)

        assert not temp_audio.exists()
        assert local_audio.exists()
        assert os.path.isdir(in_tmp_cwd / "output")
        warning_mock.assert_not_called()
