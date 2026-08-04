"""
WebUI向けの非同期実行・SRT整形ラッパー層(設計書: 作から計への設計書_WebUIフレームワーク選定と
プロトタイプ方針_20260806.md §5・§6準拠)。

`core/transcription_interface.py` / `core/cli_workflow.py` の既存関数は変更せず、
ここから呼び出すのみに留める(クラス抽象化方針)。
"""

from __future__ import annotations

import queue
import threading
from typing import TYPE_CHECKING, Any, List, Optional

if TYPE_CHECKING:
    from core.transcription_interface import TranscriptionResult, TranscriptionSegment, UnifiedTranscriber


class TranscriptionJob:
    """バックグラウンドスレッドで実行中の文字起こしジョブの状態を保持する。"""

    def __init__(self) -> None:
        self.thread: Optional[threading.Thread] = None
        self.progress_queue: "queue.Queue[str]" = queue.Queue()
        self.result: Optional["TranscriptionResult"] = None
        self.error: Optional[BaseException] = None
        self.done: bool = False


def start_transcription_job(transcriber: "UnifiedTranscriber", audio_path: str, **kwargs: Any) -> TranscriptionJob:
    """`UnifiedTranscriber.transcribe()` を別スレッドで実行し、進捗をqueue経由で共有する。

    `UnifiedTranscriber.transcribe()` 自体は変更しない(設計書§5)。既存の
    `progress_callback` 引数(`core/transcription_interface.py`)を利用して
    進捗メッセージをqueueへ流し込む。
    """
    job = TranscriptionJob()

    def _progress_callback(message: str) -> None:
        job.progress_queue.put(message)

    def _run() -> None:
        try:
            job.result = transcriber.transcribe(
                audio_path, progress_callback=_progress_callback, **kwargs
            )
        except BaseException as e:  # noqa: BLE001 - ジョブの失敗をUI側へそのまま伝える
            job.error = e
        finally:
            job.done = True

    thread = threading.Thread(target=_run, daemon=True)
    job.thread = thread
    thread.start()
    return job


def drain_progress(job: TranscriptionJob) -> List[str]:
    """キューに溜まった進捗メッセージを全て取り出す(ノンブロッキング)。"""
    messages: List[str] = []
    while True:
        try:
            messages.append(job.progress_queue.get_nowait())
        except queue.Empty:
            break
    return messages


def segments_to_srt(segments: List["TranscriptionSegment"]) -> str:
    """`TranscriptionSegment` のリストをSRT形式の文字列に変換する(設計書§3-4)。

    `include_timestamps=True`(ForcedAligner使用)時のみ意味のある区間が得られる。
    空リストの場合は空文字列を返す。
    """
    if not segments:
        return ""

    def _format_timestamp(seconds: float) -> str:
        seconds = max(0.0, seconds)
        total_ms = round(seconds * 1000)
        hours, rem_ms = divmod(total_ms, 3_600_000)
        minutes, rem_ms = divmod(rem_ms, 60_000)
        secs, ms = divmod(rem_ms, 1000)
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{ms:03d}"

    lines: List[str] = []
    for i, seg in enumerate(segments, start=1):
        lines.append(str(i))
        lines.append(f"{_format_timestamp(seg.start)} --> {_format_timestamp(seg.end)}")
        lines.append(seg.text)
        lines.append("")
    return "\n".join(lines)
