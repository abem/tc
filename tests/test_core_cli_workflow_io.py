"""
Tests for `core/cli_workflow.py` の入力解決・結果アップロード・履歴記録
(tc-ops #567 Task 2.3、リファクタリング前の現挙動の固定化)。

- `resolve_input_audio`: gdrive / local / unknown 分岐(youtube分岐は
  tests/test_webui_duplicate_url_download.py が担当)
- `upload_transcription_result`: youtube / gdrive / それ以外の分岐と、Drive呼び出しの引数・失敗時挙動
- `record_transcription_history`: tmp_path上のSQLiteへのINSERT内容(FTS5同期の検証は
  tests/test_core_cli_workflow_history_fts.py が担当)

実Drive API・実ネットワークは使わない。`handlers.gdrive.GDriveClient` は関数内importのため、
`handlers.gdrive.GDriveClient` 属性を差し替える。
"""

import sqlite3
from unittest.mock import patch

import pytest

from core.cli_workflow import (
    InputResolution,
    record_transcription_history,
    resolve_input_audio,
    upload_transcription_result,
)
from core.transcription_interface import TranscriptionResult

GDRIVE_URL = "https://drive.google.com/file/d/FILEID123/view?usp=sharing"


# ---------------------------------------------------------------------------
# resolve_input_audio
# ---------------------------------------------------------------------------
class TestResolveInputAudioGdrive:
    def test_gdrive_url_downloads_via_client_and_returns_resolution(self, tmp_path):
        downloaded = tmp_path / "downloaded.mp3"
        statuses = []
        with patch("handlers.gdrive.GDriveClient") as client_cls:
            client_cls.return_value.download.return_value = downloaded

            res = resolve_input_audio(GDRIVE_URL, tmp_path / "out", on_status=statuses.append)

        client_cls.assert_called_once_with()
        client_cls.return_value.download.assert_called_once_with(GDRIVE_URL)
        assert isinstance(res, InputResolution)
        assert res.source_type == "gdrive"
        assert res.original_source == GDRIVE_URL
        assert res.local_audio_path == str(downloaded)
        assert isinstance(res.local_audio_path, str)
        # 現挙動: gdrive由来のDLファイルでも is_temp_file は False
        # (webui.py は source_type == "gdrive" で別途cleanup判定している)
        assert res.is_temp_file is False
        assert res.metadata is None
        assert res.youtube_handler is None
        assert statuses == ["Google Drive URLを検出、ダウンロードを開始"]

    def test_gdrive_without_on_status_does_not_fail(self, tmp_path):
        with patch("handlers.gdrive.GDriveClient") as client_cls:
            client_cls.return_value.download.return_value = tmp_path / "a.mp3"

            res = resolve_input_audio(GDRIVE_URL, tmp_path)

        assert res.source_type == "gdrive"

    def test_gdrive_does_not_touch_youtube_client(self, tmp_path):
        with patch("handlers.gdrive.GDriveClient") as client_cls, patch(
            "handlers.youtube.YouTubeClient"
        ) as yt_cls:
            client_cls.return_value.download.return_value = tmp_path / "a.mp3"

            resolve_input_audio(GDRIVE_URL, tmp_path)

        yt_cls.assert_not_called()

    def test_gdrive_download_error_propagates(self, tmp_path):
        with patch("handlers.gdrive.GDriveClient") as client_cls:
            client_cls.return_value.download.side_effect = RuntimeError("download failed")

            with pytest.raises(RuntimeError, match="download failed"):
                resolve_input_audio(GDRIVE_URL, tmp_path)


class TestResolveInputAudioLocal:
    def test_existing_local_file_is_returned_as_is(self, tmp_path):
        audio = tmp_path / "sample.wav"
        audio.write_bytes(b"RIFF")
        statuses = []

        res = resolve_input_audio(str(audio), tmp_path / "out", on_status=statuses.append)

        assert res.source_type == "local"
        assert res.original_source == str(audio)
        assert res.local_audio_path == str(audio)
        assert res.is_temp_file is False
        assert res.metadata is None
        assert res.youtube_handler is None
        # local分岐は status を呼ばない
        assert statuses == []

    def test_local_does_not_create_output_dir_nor_call_clients(self, tmp_path):
        audio = tmp_path / "sample.wav"
        audio.write_bytes(b"RIFF")
        out_dir = tmp_path / "out"

        with patch("handlers.gdrive.GDriveClient") as gd, patch("handlers.youtube.YouTubeClient") as yt:
            resolve_input_audio(str(audio), out_dir)

        gd.assert_not_called()
        yt.assert_not_called()
        assert not out_dir.exists()


class TestResolveInputAudioUnknown:
    def test_nonexistent_path_raises_value_error(self, tmp_path):
        missing = str(tmp_path / "no_such_file.wav")

        with pytest.raises(ValueError) as exc_info:
            resolve_input_audio(missing, tmp_path)

        assert str(exc_info.value) == f"入力を認識できません: {missing}"

    def test_unsupported_string_raises_value_error(self, tmp_path):
        with pytest.raises(ValueError, match="入力を認識できません: not a url or path"):
            resolve_input_audio("not a url or path", tmp_path)

    def test_non_gdrive_url_is_unknown(self, tmp_path):
        """http://drive... (httpsでない) や他サイトのURLは対応外。"""
        with pytest.raises(ValueError, match="入力を認識できません"):
            resolve_input_audio("https://example.com/audio.mp3", tmp_path)

    def test_unknown_does_not_call_status(self, tmp_path):
        statuses = []
        with pytest.raises(ValueError):
            resolve_input_audio("nonexistent-input", tmp_path, on_status=statuses.append)

        assert statuses == []


# ---------------------------------------------------------------------------
# upload_transcription_result
# ---------------------------------------------------------------------------
class TestUploadTranscriptionResultGdrive:
    def test_gdrive_uploads_to_sibling_folder_and_returns_url(self, tmp_path):
        out = tmp_path / "result.txt"
        out.write_text("text", encoding="utf-8")
        with patch("handlers.gdrive.GDriveClient") as client_cls:
            client = client_cls.return_value
            client.get_parent_folder_id.return_value = "PARENT_ID"
            client.upload_file.return_value = "UPLOADED_ID"
            client.get_file_url.return_value = "https://drive.google.com/file/d/UPLOADED_ID/view"

            url = upload_transcription_result(
                source_type="gdrive", original_source=GDRIVE_URL, output_file=out
            )

        assert url == "https://drive.google.com/file/d/UPLOADED_ID/view"
        client.get_parent_folder_id.assert_called_once_with("FILEID123")
        client.upload_file.assert_called_once_with(str(out), "result.txt", parent_id="PARENT_ID")
        client.get_file_url.assert_called_once_with("UPLOADED_ID")

    def test_folder_id_override_skips_parent_lookup(self, tmp_path):
        out = tmp_path / "result.txt"
        out.write_text("text", encoding="utf-8")
        with patch("handlers.gdrive.GDriveClient") as client_cls:
            client = client_cls.return_value
            client.upload_file.return_value = "UPLOADED_ID"
            client.get_file_url.return_value = "URL"

            url = upload_transcription_result(
                source_type="gdrive",
                original_source=GDRIVE_URL,
                output_file=out,
                folder_id="OVERRIDE_FOLDER",
            )

        assert url == "URL"
        client.get_parent_folder_id.assert_not_called()
        client.upload_file.assert_called_once_with(str(out), "result.txt", parent_id="OVERRIDE_FOLDER")

    def test_id_query_style_url_is_supported(self, tmp_path):
        out = tmp_path / "result.txt"
        with patch("handlers.gdrive.GDriveClient") as client_cls:
            client = client_cls.return_value
            client.get_parent_folder_id.return_value = "P"
            client.upload_file.return_value = "U"
            client.get_file_url.return_value = "URL"

            upload_transcription_result(
                source_type="gdrive",
                original_source="https://drive.google.com/open?id=QUERYID9",
                output_file=out,
            )

        client.get_parent_folder_id.assert_called_once_with("QUERYID9")

    def test_gdrive_url_without_file_id_returns_none_without_client(self, tmp_path):
        out = tmp_path / "result.txt"
        with patch("handlers.gdrive.GDriveClient") as client_cls:
            url = upload_transcription_result(
                source_type="gdrive",
                original_source="https://drive.google.com/drive/folders/FOLDERONLY",
                output_file=out,
            )

        assert url is None
        client_cls.assert_not_called()

    def test_get_file_url_none_is_returned_as_none(self, tmp_path):
        out = tmp_path / "result.txt"
        with patch("handlers.gdrive.GDriveClient") as client_cls:
            client = client_cls.return_value
            client.get_parent_folder_id.return_value = "P"
            client.upload_file.return_value = "U"
            client.get_file_url.return_value = None

            url = upload_transcription_result(
                source_type="gdrive", original_source=GDRIVE_URL, output_file=out
            )

        assert url is None

    def test_upload_failure_propagates(self, tmp_path):
        """アップロード失敗は握らず呼び出し元(各CLIの保存処理のtry/except)へ伝播する。"""
        out = tmp_path / "result.txt"
        with patch("handlers.gdrive.GDriveClient") as client_cls:
            client = client_cls.return_value
            client.get_parent_folder_id.return_value = "P"
            client.upload_file.side_effect = RuntimeError("upload failed")

            with pytest.raises(RuntimeError, match="upload failed"):
                upload_transcription_result(
                    source_type="gdrive", original_source=GDRIVE_URL, output_file=out
                )

        client.get_file_url.assert_not_called()


class TestUploadTranscriptionResultYoutube:
    def test_youtube_uploads_with_metadata_and_returns_file_url(self, tmp_path):
        out = tmp_path / "result.txt"
        meta = {"title": "T", "video_id": "abc"}
        with patch("handlers.gdrive.GDriveClient") as client_cls:
            client = client_cls.return_value
            client.upload_youtube_transcription.return_value = {"file_url": "https://example/x"}

            url = upload_transcription_result(
                source_type="youtube",
                original_source="https://www.youtube.com/watch?v=abc",
                output_file=out,
                metadata=meta,
            )

        assert url == "https://example/x"
        client.upload_youtube_transcription.assert_called_once_with(str(out), meta)

    @pytest.mark.parametrize("metadata", [None, {}])
    def test_youtube_without_metadata_returns_none_without_client(self, tmp_path, metadata):
        with patch("handlers.gdrive.GDriveClient") as client_cls:
            url = upload_transcription_result(
                source_type="youtube",
                original_source="https://www.youtube.com/watch?v=abc",
                output_file=tmp_path / "result.txt",
                metadata=metadata,
            )

        assert url is None
        client_cls.assert_not_called()

    @pytest.mark.parametrize("upload_result", [None, {}])
    def test_youtube_empty_upload_result_returns_none(self, tmp_path, upload_result):
        with patch("handlers.gdrive.GDriveClient") as client_cls:
            client_cls.return_value.upload_youtube_transcription.return_value = upload_result

            url = upload_transcription_result(
                source_type="youtube",
                original_source="https://www.youtube.com/watch?v=abc",
                output_file=tmp_path / "result.txt",
                metadata={"title": "T"},
            )

        assert url is None

    def test_youtube_result_without_file_url_key_returns_none(self, tmp_path):
        with patch("handlers.gdrive.GDriveClient") as client_cls:
            client_cls.return_value.upload_youtube_transcription.return_value = {"folder_id": "F"}

            url = upload_transcription_result(
                source_type="youtube",
                original_source="https://www.youtube.com/watch?v=abc",
                output_file=tmp_path / "result.txt",
                metadata={"title": "T"},
            )

        assert url is None

    def test_youtube_upload_failure_propagates(self, tmp_path):
        with patch("handlers.gdrive.GDriveClient") as client_cls:
            client_cls.return_value.upload_youtube_transcription.side_effect = RuntimeError("yt upload failed")

            with pytest.raises(RuntimeError, match="yt upload failed"):
                upload_transcription_result(
                    source_type="youtube",
                    original_source="https://www.youtube.com/watch?v=abc",
                    output_file=tmp_path / "result.txt",
                    metadata={"title": "T"},
                )


class TestUploadTranscriptionResultOtherSources:
    @pytest.mark.parametrize("source_type", ["local", "twitter", "unknown", ""])
    def test_non_drive_sources_return_none_without_touching_drive(self, tmp_path, source_type):
        """local / twitter 等、gdrive・youtube以外はアップロードせず None。"""
        with patch("handlers.gdrive.GDriveClient") as client_cls:
            url = upload_transcription_result(
                source_type=source_type,
                original_source="whatever",
                output_file=tmp_path / "result.txt",
                metadata={"title": "T"},
                folder_id="F",
            )

        assert url is None
        client_cls.assert_not_called()


# ---------------------------------------------------------------------------
# record_transcription_history
# ---------------------------------------------------------------------------
_COLUMNS = [
    "id", "processed_at", "source_type", "source_original", "source_title", "model_name",
    "device", "language", "diarization_enabled", "include_timestamps", "context_hints_used",
    "char_count", "duration_sec", "processing_time_sec", "failed_chunks", "repeated_chunks",
    "result_text", "output_text_path", "gdrive_url", "notes",
]


def _make_result(text="こんにちは世界", metadata=None, **overrides):
    kwargs = dict(
        text=text,
        segments=[],
        language="ja",
        duration=12.5,
        processing_time=3.25,
        model_name="test/model",
        metadata=metadata,
    )
    kwargs.update(overrides)
    return TranscriptionResult(**kwargs)


def _make_resolution(**overrides):
    kwargs = dict(
        source_type="local",
        original_source="/path/to/audio.wav",
        local_audio_path="/path/to/audio.wav",
        is_temp_file=False,
        metadata=None,
        youtube_handler=None,
    )
    kwargs.update(overrides)
    return InputResolution(**kwargs)


def _fetch_rows(db_path):
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in conn.execute("SELECT * FROM transcription_history ORDER BY id")]
    finally:
        conn.close()


class TestRecordTranscriptionHistory:
    def test_inserts_row_with_all_columns(self, tmp_path):
        db = tmp_path / "hist" / "history.db"
        result = _make_result(metadata={"failed_chunks": 2, "repeated_chunks": 1})
        resolution = _make_resolution(
            source_type="youtube",
            original_source="https://www.youtube.com/watch?v=abc",
            metadata={"title": "動画タイトル"},
        )
        settings = {"device": "cuda", "diarization": True, "include_timestamps": True, "context": "固有名詞"}

        record_transcription_history(
            result=result,
            resolution=resolution,
            output_file=tmp_path / "out.txt",
            settings=settings,
            gdrive_url="https://drive.google.com/file/d/X/view",
            db_path=db,
        )

        rows = _fetch_rows(db)
        assert len(rows) == 1
        row = rows[0]
        assert list(row.keys()) == _COLUMNS
        assert row["id"] == 1
        assert row["source_type"] == "youtube"
        assert row["source_original"] == "https://www.youtube.com/watch?v=abc"
        assert row["source_title"] == "動画タイトル"
        assert row["model_name"] == "test/model"
        assert row["device"] == "cuda"
        assert row["language"] == "ja"
        assert row["diarization_enabled"] == 1
        assert row["include_timestamps"] == 1
        assert row["context_hints_used"] == 1
        assert row["char_count"] == len("こんにちは世界")
        assert row["duration_sec"] == 12.5
        assert row["processing_time_sec"] == 3.25
        assert row["failed_chunks"] == 2
        assert row["repeated_chunks"] == 1
        assert row["result_text"] == "こんにちは世界"
        assert row["output_text_path"] == str(tmp_path / "out.txt")
        assert row["gdrive_url"] == "https://drive.google.com/file/d/X/view"
        assert row["notes"] is None
        # ISO8601 秒精度(例: 2026-10-02T12:34:56)
        assert len(row["processed_at"]) == 19 and row["processed_at"][10] == "T"

    def test_defaults_when_settings_and_metadata_are_empty(self, tmp_path):
        db = tmp_path / "history.db"

        record_transcription_history(
            result=_make_result(metadata=None),
            resolution=_make_resolution(metadata=None),
            output_file=tmp_path / "out.txt",
            settings={},
            db_path=db,
        )

        row = _fetch_rows(db)[0]
        assert row["source_title"] is None
        assert row["device"] == ""
        assert row["diarization_enabled"] == 0
        assert row["include_timestamps"] == 0
        assert row["context_hints_used"] == 0
        assert row["failed_chunks"] == 0
        assert row["repeated_chunks"] == 0
        assert row["gdrive_url"] is None

    def test_none_and_empty_settings_values_are_falsy(self, tmp_path):
        db = tmp_path / "history.db"

        record_transcription_history(
            result=_make_result(),
            resolution=_make_resolution(),
            output_file=tmp_path / "out.txt",
            settings={"device": None, "context": None, "diarization": False, "include_timestamps": False},
            db_path=db,
        )

        row = _fetch_rows(db)[0]
        assert row["device"] == ""
        assert row["context_hints_used"] == 0
        assert row["diarization_enabled"] == 0
        assert row["include_timestamps"] == 0

    def test_resolution_metadata_without_title_gives_none_title(self, tmp_path):
        db = tmp_path / "history.db"

        record_transcription_history(
            result=_make_result(),
            resolution=_make_resolution(metadata={"video_id": "abc"}),
            output_file=tmp_path / "out.txt",
            settings={},
            db_path=db,
        )

        assert _fetch_rows(db)[0]["source_title"] is None

    def test_empty_text_gives_zero_char_count(self, tmp_path):
        db = tmp_path / "history.db"

        record_transcription_history(
            result=_make_result(text=""),
            resolution=_make_resolution(),
            output_file=tmp_path / "out.txt",
            settings={},
            db_path=db,
        )

        row = _fetch_rows(db)[0]
        assert row["char_count"] == 0
        assert row["result_text"] == ""

    def test_second_record_appends_a_new_row(self, tmp_path):
        db = tmp_path / "history.db"
        for i, text in enumerate(["一件目のテキスト", "二件目のテキスト"]):
            record_transcription_history(
                result=_make_result(text=text),
                resolution=_make_resolution(original_source=f"/audio{i}.wav"),
                output_file=tmp_path / f"out{i}.txt",
                settings={"device": "cpu"},
                db_path=db,
            )

        rows = _fetch_rows(db)
        assert [r["id"] for r in rows] == [1, 2]
        assert [r["result_text"] for r in rows] == ["一件目のテキスト", "二件目のテキスト"]
        assert [r["source_original"] for r in rows] == ["/audio0.wav", "/audio1.wav"]

    def test_creates_parent_directory_and_tables_including_fts(self, tmp_path):
        db = tmp_path / "a" / "b" / "history.db"
        assert not db.parent.exists()

        record_transcription_history(
            result=_make_result(text="検索対象テキスト"),
            resolution=_make_resolution(),
            output_file=tmp_path / "out.txt",
            settings={},
            db_path=db,
        )

        conn = sqlite3.connect(str(db))
        try:
            names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master")}
            assert {"transcription_history", "transcription_history_fts"} <= names
            # ensure_history_table との連携: 記録した行がFTSトリガーで同期され検索可能
            hits = conn.execute(
                "SELECT rowid FROM transcription_history_fts WHERE transcription_history_fts MATCH ?",
                ('"検索対象"',),
            ).fetchall()
        finally:
            conn.close()
        assert [h[0] for h in hits] == [1]

    def test_records_into_existing_db_created_by_ensure_history_table(self, tmp_path):
        from core.cli_workflow import ensure_history_table

        db = tmp_path / "history.db"
        conn = sqlite3.connect(str(db))
        ensure_history_table(conn)
        conn.close()

        record_transcription_history(
            result=_make_result(),
            resolution=_make_resolution(),
            output_file=tmp_path / "out.txt",
            settings={},
            db_path=db,
        )

        assert len(_fetch_rows(db)) == 1

    def test_error_before_insert_propagates_and_leaves_no_row(self, tmp_path):
        """`result.text` が str でない等でINSERT前に例外が出ても握らず伝播する
        (呼び出し元が独立try/exceptで囲む前提の契約)。"""
        db = tmp_path / "history.db"
        bad_result = _make_result()
        bad_result.text = None  # len(None) -> TypeError

        with pytest.raises(TypeError):
            record_transcription_history(
                result=bad_result,
                resolution=_make_resolution(),
                output_file=tmp_path / "out.txt",
                settings={},
                db_path=db,
            )

        assert _fetch_rows(db) == []
