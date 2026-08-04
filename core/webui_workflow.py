"""
WebUI向けの非同期実行・SRT整形ラッパー層(設計書: 作から計への設計書_WebUIフレームワーク選定と
プロトタイプ方針_20260806.md §5・§6準拠)。

`core/transcription_interface.py` / `core/cli_workflow.py` の既存関数は変更せず、
ここから呼び出すのみに留める(クラス抽象化方針)。
"""

from __future__ import annotations

import queue
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional

if TYPE_CHECKING:
    from core.cli_workflow import InputResolution
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


class QueueItemState(Enum):
    """ジョブキュー項目の状態(予備調査#440・4-1節「ジョブ状態遷移」)。"""

    QUEUED = "queued"
    PROCESSING = "processing"
    DONE = "done"
    FAILED = "failed"


@dataclass
class QueueItem:
    """ジョブキューの1項目。投入内容の解決結果(`resolution`)を各項目が専有することで、
    完了時のクリーンアップ(`_cleanup_temp_file()`)が他項目へ波及しないことを構造的に担保する
    (予備調査#440・4-1節「既存の一時ファイル削除処理への影響」)。"""

    label: str
    resolution: "InputResolution"
    settings: Dict[str, Any]
    item_id: int = 0
    state: QueueItemState = QueueItemState.QUEUED
    job: Optional[TranscriptionJob] = None
    log: List[str] = field(default_factory=list)
    submitted_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    finished_at: Optional[float] = None
    output_file: Optional[str] = None
    gdrive_url: Optional[str] = None
    error_message: Optional[str] = None


class TranscriptionJobQueue:
    """複数の文字起こしジョブを逐次処理するためのキュー(WebUI用、tc-ops #440)。

    同時実行は1件のみ(GPU/モデルが1インスタンスのみの制約により並列実行は対象外)。
    `dispatch_next()` を定期的に呼び出すことで、処理中ジョブが無いときに次の待機項目を
    自動的に起動する。
    """

    def __init__(self) -> None:
        self.items: List[QueueItem] = []
        self._next_id: int = 1

    def enqueue(self, label: str, resolution: "InputResolution", settings: Dict[str, Any]) -> QueueItem:
        """新規項目を`QUEUED`状態でキュー末尾に追加する(実行中ジョブがあっても追加投入可能)。"""
        item = QueueItem(label=label, resolution=resolution, settings=dict(settings), item_id=self._next_id)
        self._next_id += 1
        self.items.append(item)
        return item

    @property
    def current(self) -> Optional[QueueItem]:
        for item in self.items:
            if item.state is QueueItemState.PROCESSING:
                return item
        return None

    @property
    def queued(self) -> List[QueueItem]:
        return [item for item in self.items if item.state is QueueItemState.QUEUED]

    @property
    def finished(self) -> List[QueueItem]:
        return [item for item in self.items if item.state in (QueueItemState.DONE, QueueItemState.FAILED)]

    def dispatch_next(self, starter: Callable[["QueueItem"], TranscriptionJob]) -> Optional[QueueItem]:
        """処理中の項目が無ければ、先頭の待機項目を`starter`で起動し`PROCESSING`へ遷移する。

        処理中の項目がある間は何もしない(逐次処理・並列実行対象外)。`starter` は
        `QueueItem` を受け取り `TranscriptionJob` を返す呼び出し可能オブジェクト
        (本番では `start_transcription_job()` をラップしたもの、テストではモック)。
        """
        if self.current is not None:
            return None
        pending = self.queued
        if not pending:
            return None
        item = pending[0]
        item.job = starter(item)
        item.state = QueueItemState.PROCESSING
        item.started_at = time.time()
        return item

    def mark_done(self, item: QueueItem, *, output_file: Optional[str], gdrive_url: Optional[str]) -> None:
        """処理中項目を完了(`DONE`)へ遷移する。"""
        item.state = QueueItemState.DONE
        item.output_file = output_file
        item.gdrive_url = gdrive_url
        item.finished_at = time.time()

    def mark_failed(self, item: QueueItem, *, error_message: str) -> None:
        """処理中項目を失敗(`FAILED`)へ遷移する。後続の`QUEUED`項目の起動は妨げない。"""
        item.state = QueueItemState.FAILED
        item.error_message = error_message
        item.finished_at = time.time()


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
