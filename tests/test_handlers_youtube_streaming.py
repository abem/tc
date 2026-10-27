"""yt-dlp の出力の読み取り: 進捗通知の遅れとパイプ詰まり(デッドロック)の防止 (tc-ops #578 独立レビュー指摘)。

旧実装は fd を select で待ちながら行はバッファ越しに readline していたため、1 回の書き込みで届いた
複数行のうち 2 行目以降が、次の出力まで通知されなかった。また stderr を読まないため、
大量の stderr を出されると子プロセスが書き込みで止まり、親は stdout を待ち続けた。
"""

import json
import stat
import sys
import textwrap
import time

import pytest

from handlers import youtube
from handlers.youtube import YouTubeClient

URL = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
INFO = {"id": "abc", "title": "T", "duration": 1, "channel": "c", "upload_date": "20260101", "description": ""}

SCRIPT = textwrap.dedent(
    """\
    #!{python}
    import json, sys, time
    args = sys.argv[1:]
    if "--dump-json" in args:
        sys.stdout.write({info!r})
        sys.exit(0)
    out = args[args.index("-o") + 1]
    {body}
    """
)


def _client(tmp_path, body):
    script = tmp_path / "fake-yt-dlp"
    script.write_text(
        SCRIPT.format(python=sys.executable, info=json.dumps(INFO), body=textwrap.dedent(body).strip()),
        encoding="utf-8",
    )
    script.chmod(script.stat().st_mode | stat.S_IXUSR)
    client = YouTubeClient(output_dir=str(tmp_path))
    client.yt_dlp_path = str(script)
    return client


def test_lines_written_together_are_notified_without_waiting_for_the_next_output(tmp_path):
    client = _client(
        tmp_path,
        """
        sys.stdout.write("[download]  10.0% of 1MiB\\n[download]  20.0% of 1MiB\\n[download]  30.0% of 1MiB\\n")
        sys.stdout.flush()
        time.sleep(2.5)
        open(out, "wb").write(b"x")
        """,
    )
    seen = []
    start = time.monotonic()

    client.download_audio(URL, output_path=str(tmp_path / "o.wav"), progress_callback=lambda m: seen.append((time.monotonic() - start, str(m))))

    at = {m: t for t, m in seen}
    assert any("30%" in m for m in at), seen
    third = next(t for m, t in at.items() if "30%" in m)
    assert third < 1.5, f"3行目の通知が遅れた: {third:.2f}s {seen}"


def test_large_stderr_does_not_stall_the_download(tmp_path, monkeypatch):
    monkeypatch.setattr(youtube, "DOWNLOAD_STALL_TIMEOUT_SECONDS", 3)
    client = _client(
        tmp_path,
        """
        sys.stderr.write("noise\\n" * 100000 + "ERROR: real failure\\n")
        sys.stderr.flush()
        print("[download] 100% of 1MiB", flush=True)
        sys.exit(1)
        """,
    )

    start = time.monotonic()
    with pytest.raises(RuntimeError, match="Audio extraction failed"):
        client.download_audio(URL, output_path=str(tmp_path / "o.wav"))
    assert time.monotonic() - start < 10


def test_stderr_error_text_is_still_reported(tmp_path):
    client = _client(
        tmp_path,
        """
        sys.stderr.write("ERROR: boom\\n")
        sys.exit(1)
        """,
    )
    with pytest.raises(RuntimeError, match="boom"):
        client.download_audio(URL, output_path=str(tmp_path / "o.wav"))


def test_stalled_output_is_killed(tmp_path, monkeypatch):
    monkeypatch.setattr(youtube, "DOWNLOAD_STALL_TIMEOUT_SECONDS", 1)
    client = _client(tmp_path, "time.sleep(30)")
    start = time.monotonic()
    with pytest.raises(TimeoutError):
        client.download_audio(URL, output_path=str(tmp_path / "o.wav"))
    assert time.monotonic() - start < 10
