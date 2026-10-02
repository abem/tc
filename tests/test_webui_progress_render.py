"""WebUIのキュー状態表示が、進捗バー(または経過時間)を出すことの描画テスト。

streamlit.testing.v1.AppTestで実際のwebui.pyを描画する。ジョブキューにだけ状態を仕込み、
ダウンロード・文字起こしは起動しない。
"""

import time
from pathlib import Path
from unittest.mock import MagicMock

from streamlit.testing.v1 import AppTest

from core.progress import ProgressMessage
from core.webui_workflow import TranscriptionJobQueue, apply_progress

WEBUI_PATH = Path(__file__).resolve().parents[1] / "webui.py"


def _render(queue: TranscriptionJobQueue) -> AppTest:
    at = AppTest.from_file(str(WEBUI_PATH), default_timeout=30)
    at.session_state["job_queue"] = queue
    at.run()
    assert at.exception == []
    return at


def _texts(at: AppTest) -> str:
    parts = [e.value for e in at.info] + [e.value for e in at.markdown] + [e.value for e in at.caption]
    return "\n".join(str(p) for p in parts)


def test_resolving_item_shows_download_progress_bar():
    queue = TranscriptionJobQueue()
    item = queue.enqueue_pending("https://x.com/u/status/1/video/1", {})
    item.submitted_at = time.time() - 125  # 経過2分5秒
    apply_progress(item, ProgressMessage("ダウンロード中 40%(残り 03:00)", 0.4))

    at = _render(queue)

    bars = at.get("progress")
    assert len(bars) == 1
    assert bars[0].proto.value == 40
    assert "ダウンロード中 40%" in bars[0].proto.text
    assert "経過 2:0" in bars[0].proto.text  # 2:05前後(描画時刻により数秒ずれる)
    assert "残り約" in bars[0].proto.text


def test_resolving_item_without_fraction_shows_elapsed_instead_of_bar():
    queue = TranscriptionJobQueue()
    item = queue.enqueue_pending("https://x.com/u/status/1/video/1", {})
    item.submitted_at = time.time() - 61
    apply_progress(item, ProgressMessage("音声をwavに変換中(長い動画は数分かかります)"))

    at = _render(queue)

    assert at.get("progress") == []
    assert "音声をwavに変換中" in _texts(at)
    assert "経過 1:0" in _texts(at)


def test_processing_item_shows_chunk_progress_bar():
    queue = TranscriptionJobQueue()
    item = queue.enqueue_pending("long.wav", {})
    queue.resolve_success(item, resolution=MagicMock())
    job = MagicMock()
    job.done = False
    job.progress_queue.get_nowait.side_effect = __import__("queue").Empty
    queue.dispatch_next(lambda _item: job)
    item.started_at = time.time() - 300
    apply_progress(item, ProgressMessage("文字起こし中 6/23 チャンク完了", 6 / 23))

    at = _render(queue)

    bars = at.get("progress")
    assert len(bars) == 1
    assert bars[0].proto.value == int(6 / 23 * 100)
    assert "6/23" in bars[0].proto.text
    assert "経過 5:0" in bars[0].proto.text
