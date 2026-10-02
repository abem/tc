"""ログとキュー表示にクライアント由来の文字列(アップロード名・URL)をそのまま出さない(tc-ops #578)。

改行を含む名前で、ログに偽の行を紛れ込ませる(ログインジェクション)ことができたため。
"""

import logging
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import webui
from core.utils import one_line
from core.webui_workflow import TranscriptionJobQueue


class TestOneLine:
    def test_plain_text_is_unchanged(self):
        assert one_line("会議 録音.wav") == "会議 録音.wav"
        assert one_line("https://example.com/watch?v=abc") == "https://example.com/watch?v=abc"

    @pytest.mark.parametrize(
        "raw, expected",
        [
            ("a\nb", "a\\nb"),
            ("a\r\nb", "a\\r\\nb"),
            ("a\tb", "a\\tb"),
            ("a\x00b", "a\\x00b"),
            ("a\x1b[31mred", "a\\x1b[31mred"),
            ("a\x7fb", "a\\x7fb"),
        ],
    )
    def test_control_characters_become_visible_escapes(self, raw, expected):
        result = one_line(raw)

        assert result == expected
        assert "\n" not in result and "\r" not in result

    def test_long_text_is_truncated_with_marker(self):
        result = one_line("a" * 500, limit=50)

        assert len(result) == 50
        assert result.endswith("…")

    def test_non_string_is_converted(self):
        assert one_line(None) == "None"
        assert one_line(123) == "123"


class TestEnqueueDoesNotLogRawNames:
    EVIL = "evil.wav\n2026-01-01 00:00:00 - core - ERROR - FAKE LINE injected"

    def _enqueue(self, monkeypatch, form):
        queue = TranscriptionJobQueue()
        monkeypatch.setattr(webui, "_get_queue", lambda: queue)
        monkeypatch.setattr(webui, "_start_resolution_job", MagicMock())
        monkeypatch.setattr(webui, "_sweep_old_files", MagicMock())
        monkeypatch.setattr(webui, "resolve_device", lambda d: "cpu")
        webui._enqueue_job(form, {"device": "cpu", "model": "m", "language": "ja", "include_timestamps": False}, "")
        return queue

    def test_upload_name_with_newline_never_splits_a_log_line(self, monkeypatch, caplog):
        form = {"source_url": "", "uploaded_file": SimpleNamespace(name=self.EVIL, getbuffer=lambda: b"")}

        with caplog.at_level(logging.INFO):
            queue = self._enqueue(monkeypatch, form)

        assert queue.items, "投入されること"
        assert "\n" not in queue.items[0].label
        for record in caplog.records:
            assert "\n" not in record.getMessage(), record.getMessage()
        assert any("evil.wav" in r.getMessage() for r in caplog.records)  # 情報は残る(エスケープされて)

    def test_url_with_control_characters_never_splits_a_log_line(self, monkeypatch, caplog):
        form = {"source_url": "https://example.com/\nFAKE LINE\x1b[2J", "uploaded_file": None}

        with caplog.at_level(logging.INFO):
            queue = self._enqueue(monkeypatch, form)

        assert "\n" not in queue.items[0].label and "\x1b" not in queue.items[0].label
        for record in caplog.records:
            assert "\n" not in record.getMessage() and "\x1b" not in record.getMessage()

    def test_normal_label_is_unchanged(self, monkeypatch):
        form = {"source_url": "", "uploaded_file": SimpleNamespace(name="会議 録音.wav", getbuffer=lambda: b"")}

        queue = self._enqueue(monkeypatch, form)

        assert queue.items[0].label == "会議 録音.wav"
