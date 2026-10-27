"""独立レビュー(tc-ops #578)の未対応指摘: one_line の取りこぼし、gdrive/transcribe の外部文字列の素通し。"""

import io
import logging
from unittest.mock import MagicMock

import pytest
from rich.console import Console

import transcribe
from core.utils import one_line, safe_console_text
from handlers.gdrive import GDriveClient

# 改行・端末制御・見た目の偽装に使える文字(C1制御、行/段落区切り、ゼロ幅、bidi、BOM)
INVISIBLE = [
    "\x85", "\x9b", " ", " ", "​", "‍", "‎", "‏",
    "‪", "‮", "⁦", "⁩", "﻿",
]


@pytest.mark.parametrize("ch", INVISIBLE)
def test_one_line_escapes_invisible_and_c1_characters(ch):
    out = one_line(f"a{ch}b")
    assert ch not in out
    assert out.startswith("a\\") and out.endswith("b")


def test_one_line_keeps_ordinary_text_including_japanese():
    assert one_line("日本語のファイル名 (1).wav") == "日本語のファイル名 (1).wav"


def test_safe_console_text_neutralizes_rich_markup_and_newlines():
    text = safe_console_text("[red]x[/red]\n[/bogus]")
    buf = io.StringIO()
    Console(file=buf, force_terminal=False, width=200).print(text)  # MarkupError にならない
    printed = buf.getvalue()
    assert "[red]x[/red]" in printed and "[/bogus]" in printed
    assert printed.count("\n") == 1  # 末尾の改行のみ


EVIL = "evil\nFAKE 2026 - ERROR - injected\x1b[31m end"


def _assert_clean(caplog):
    assert caplog.records
    for r in caplog.records:
        m = r.getMessage()
        assert "\n" not in m and "\x1b" not in m and " " not in m, repr(m)


@pytest.fixture
def client():
    c = GDriveClient()
    c._service = MagicMock()
    c.base_folder_name = "base"
    return c


def test_gdrive_error_logs_are_one_line(client, caplog, tmp_path):
    client.service.files.return_value.get.return_value.execute.side_effect = Exception(EVIL)
    client.service.files.return_value.list.return_value.execute.side_effect = Exception(EVIL)
    client.service.files.return_value.create.return_value.execute.side_effect = Exception(EVIL)
    f = tmp_path / "t.txt"
    f.write_text("x")
    with caplog.at_level(logging.INFO):
        client.get_file_url("id")
        client.get_parent_folder_id("id")
        client.find_folder_by_name("n")
        client.create_folder("n")
        client.upload_youtube_transcription(str(f), {"title": EVIL, "video_id": "v"})
    _assert_clean(caplog)


def test_gdrive_info_logs_with_external_names_are_one_line(client, caplog):
    client.service.files.return_value.list.return_value.execute.return_value = {"files": [{"id": "I\nD"}]}
    client.service.files.return_value.create.return_value.execute.return_value = {"id": "N\nEW"}
    client.service.files.return_value.get.return_value.execute.return_value = {"parents": ["P\nAR"]}
    with caplog.at_level(logging.INFO):
        client.find_folder_by_name(EVIL)
        client.create_folder(EVIL)
        client.get_parent_folder_id("F\nID")
    _assert_clean(caplog)


class _Outcome:
    upload_error = "bad [/x]\nFAKE"
    upload_attempted = True
    gdrive_url = None
    history_error = "h [/y]\nFAKE"
    cleanup_warning = "c [/z]\nFAKE"


def test_save_results_prints_external_strings_safely(monkeypatch):
    buf = io.StringIO()
    monkeypatch.setattr(transcribe, "console", Console(file=buf, force_terminal=False, width=200))
    monkeypatch.setattr(transcribe, "finalize_transcription", lambda **kw: _Outcome())
    loader = transcribe.TranscribeLoader.__new__(transcribe.TranscribeLoader)

    loader.save_results(MagicMock(), MagicMock(), {}, None)  # rich の MarkupError を起こさない

    out = buf.getvalue()
    assert "bad [/x]" in out and "h [/y]" in out and "c [/z]" in out
    assert "\nFAKE" not in out


def _prepare_run(monkeypatch, buf, process):
    monkeypatch.setattr(transcribe, "console", Console(file=buf, force_terminal=False, width=200))
    monkeypatch.setattr(transcribe.UnifiedConfig, "load", lambda *a, **k: None)
    monkeypatch.setattr(transcribe.UnifiedConfig, "get", classmethod(lambda cls, *a, **k: None))
    monkeypatch.setattr("sys.argv", ["transcribe.py", "https://www.youtube.com/watch?v=abc123", "--profile", "3"])
    loader = transcribe.TranscribeLoader()
    monkeypatch.setattr(loader, "process_with_progress", process)
    return loader


def test_start_message_shows_the_selected_language(monkeypatch):
    buf = io.StringIO()
    loader = _prepare_run(monkeypatch, buf, lambda *a, **k: None)
    assert loader.run() == 0
    out = buf.getvalue()
    assert "言語: en" in out and "日本語音声" not in out


def test_missing_yt_dlp_exits_with_hint_instead_of_traceback(monkeypatch):
    buf = io.StringIO()

    def boom(*a, **k):
        raise transcribe.YtDlpNotFoundError("yt-dlp が見つかりません。`uv sync` を実行してください")

    loader = _prepare_run(monkeypatch, buf, boom)
    assert loader.run() == 1
    assert "uv sync" in buf.getvalue()
