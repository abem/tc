"""yt-dlp のエラー全文や例外メッセージを、複数行のままログ・例外・状態遷移ログへ出さない(tc-ops #578)。

yt-dlp の stderr は複数行になり得る(外部コマンド・外部サイトの内容を含む)。改行をそのまま出すと、
ログに偽の行を紛れ込ませられ、1 件のエラーが複数のログ行に分かれて追いにくくなる。
"""

import logging
import stat
import sys
import textwrap
from pathlib import Path
from unittest.mock import MagicMock

import pytest

import webui
from core.webui_workflow import TranscriptionJobQueue
from handlers.youtube import YouTubeClient

EVIL_STDERR = "ERROR: first line\n2026-01-01 00:00:00 - core - ERROR - FAKE injected\x1b[31m red"

FAKE_FAILING_YTDLP = textwrap.dedent(
    """\
    #!{python}
    import sys
    sys.stderr.write({stderr!r})
    sys.exit(1)
    """
)


@pytest.fixture
def failing_client(tmp_path):
    script = tmp_path / "failing-yt-dlp"
    script.write_text(FAKE_FAILING_YTDLP.format(python=sys.executable, stderr=EVIL_STDERR), encoding="utf-8")
    script.chmod(script.stat().st_mode | stat.S_IXUSR)
    client = YouTubeClient(output_dir=str(tmp_path))
    client.yt_dlp_path = str(script)
    return client


def _no_multiline(caplog):
    for record in caplog.records:
        message = record.getMessage()
        assert "\n" not in message and "\x1b" not in message, repr(message)


class TestYtDlpFailureLogs:
    def test_info_failure_log_is_one_line_and_keeps_the_content(self, failing_client, caplog):
        with caplog.at_level(logging.INFO):
            assert failing_client.extract_video_info("https://www.youtube.com/watch?v=abc") == {}

        _no_multiline(caplog)
        assert any("first line\\n2026-01-01" in r.getMessage() for r in caplog.records)

    def test_download_failure_exception_message_is_one_line(self, tmp_path, caplog):
        """情報取得は成功し、ダウンロード段階で複数行の stderr を出して失敗する場合。"""
        script = tmp_path / "half-yt-dlp"
        script.write_text(
            textwrap.dedent(
                f"""\
                #!{sys.executable}
                import sys
                if "--dump-json" in sys.argv:
                    sys.stdout.write('{{"id": "abc", "title": "t", "duration": 1}}')
                    sys.exit(0)
                sys.stderr.write({EVIL_STDERR!r})
                sys.exit(1)
                """
            ),
            encoding="utf-8",
        )
        script.chmod(script.stat().st_mode | stat.S_IXUSR)
        client = YouTubeClient(output_dir=str(tmp_path))
        client.yt_dlp_path = str(script)

        with caplog.at_level(logging.INFO), pytest.raises(RuntimeError) as excinfo:
            client.download_audio("https://www.youtube.com/watch?v=abc", output_path=str(tmp_path / "o.wav"))

        message = str(excinfo.value)
        assert "\n" not in message and "\x1b" not in message
        assert "first line\\n2026-01-01" in message
        _no_multiline(caplog)


class TestWorkflowFailureLogs:
    def test_resolve_failed_log_is_one_line(self, caplog):
        queue = TranscriptionJobQueue()
        item = queue.enqueue_pending("x", {})

        with caplog.at_level(logging.INFO):
            queue.resolve_failed(item, RuntimeError(EVIL_STDERR))

        _no_multiline(caplog)

    def test_mark_failed_log_is_one_line(self, caplog):
        queue = TranscriptionJobQueue()
        item = queue.enqueue_pending("x", {})
        queue.resolve_success(item, MagicMock())
        queue.dispatch_next(lambda _i: MagicMock())

        with caplog.at_level(logging.INFO):
            queue.mark_failed(item, error_message=EVIL_STDERR)

        _no_multiline(caplog)

    def test_error_text_shown_to_the_user_is_not_altered(self):
        """画面に出すエラー文(item.error_message)は元の文字列のまま(ログだけを1行にする)。"""
        queue = TranscriptionJobQueue()
        item = queue.enqueue_pending("x", {})

        queue.resolve_failed(item, RuntimeError("line1\nline2"))

        assert item.error_message == "line1\nline2"


class TestWebuiResolveFailureLog:
    def test_resolve_input_failure_log_is_one_line(self, tmp_path, monkeypatch, caplog):
        monkeypatch.setattr(webui, "resolve_input_audio", MagicMock(side_effect=RuntimeError(EVIL_STDERR)))

        with caplog.at_level(logging.INFO), pytest.raises(RuntimeError):
            webui._resolve_input(
                {"source_url": "https://www.youtube.com/watch?v=abc", "uploaded_file": None},
                Path(tmp_path) / "dl",
                on_status=lambda m: None,
            )

        _no_multiline(caplog)
