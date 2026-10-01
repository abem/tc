"""
core.webui_workflow の「入力解決(RESOLVING)の状態遷移」「SRT変換」「進捗取り出し」
「文字起こしジョブのスレッド実行」の現在の挙動を固定するテスト(tc-ops #567 Task 2.4)。

既存の `test_core_webui_workflow_queue.py`(enqueue / dispatch_next / mark_done / mark_failed)
と `test_core_webui_workflow_enum_reload.py`(QueueItemState の str, Enum 性質)が見ていない、
次の部分を対象とする。

- `enqueue_pending` / `resolve_success` / `resolve_failed`
- `segments_to_srt`
- `drain_progress`
- `start_transcription_job`(偽の transcriber を使い、実モデル・GPU・ネットワークは使わない)

注意: `QueueItemState` は `(str, Enum)` で、Streamlit のリロード対策(tc-ops #548)のため
状態の比較は `is` ではなく `==` で行う。本ファイルのテストも `==` で比較する。
"""

import threading
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from core.webui_workflow import (
    QueueItemState,
    TranscriptionJob,
    TranscriptionJobQueue,
    drain_progress,
    segments_to_srt,
    start_transcription_job,
)

_JOIN_TIMEOUT_SEC = 10.0


def _resolution(name: str):
    return MagicMock(name=name)


def _settings():
    return {"model": "Qwen/Qwen3-ASR-1.7B", "device": "cpu", "include_timestamps": False}


def _starter_returning(job: TranscriptionJob):
    return MagicMock(side_effect=lambda item: job)


def _seg(start: float, end: float, text: str):
    """TranscriptionSegment の代わり。segments_to_srt は start/end/text のみを参照する。"""
    return SimpleNamespace(start=start, end=end, text=text)


# --------------------------------------------------------------------------
# enqueue_pending
# --------------------------------------------------------------------------
class TestEnqueuePending:
    def test_adds_item_in_resolving_state_without_resolution(self):
        job_queue = TranscriptionJobQueue()

        item = job_queue.enqueue_pending("https://example.com/video", _settings())

        assert item.state == QueueItemState.RESOLVING
        assert item.resolution is None
        assert item.label == "https://example.com/video"
        assert item.job is None
        assert item.started_at is None
        assert item.finished_at is None
        assert item.error_message is None
        assert item.resolve_error is None
        assert job_queue.items == [item]

    def test_resolving_item_appears_only_in_resolving_property(self):
        job_queue = TranscriptionJobQueue()

        item = job_queue.enqueue_pending("a", _settings())

        assert job_queue.resolving == [item]
        assert job_queue.queued == []
        assert job_queue.current is None
        assert job_queue.finished == []

    def test_item_id_is_sequential_and_shared_with_enqueue(self):
        job_queue = TranscriptionJobQueue()

        first = job_queue.enqueue_pending("a", _settings())
        second = job_queue.enqueue("b", _resolution("b"), _settings())
        third = job_queue.enqueue_pending("c", _settings())

        assert [first.item_id, second.item_id, third.item_id] == [1, 2, 3]
        assert job_queue.items == [first, second, third]

    def test_settings_dict_is_copied_not_shared(self):
        job_queue = TranscriptionJobQueue()
        settings = _settings()

        item = job_queue.enqueue_pending("a", settings)
        settings["model"] = "changed-after-enqueue"

        assert item.settings["model"] == "Qwen/Qwen3-ASR-1.7B"

    def test_dispatch_next_ignores_resolving_item(self):
        job_queue = TranscriptionJobQueue()
        item = job_queue.enqueue_pending("a", _settings())
        starter = MagicMock()

        dispatched = job_queue.dispatch_next(starter)

        assert dispatched is None
        starter.assert_not_called()
        assert item.state == QueueItemState.RESOLVING

    def test_dispatch_next_skips_resolving_head_and_starts_queued_item(self):
        job_queue = TranscriptionJobQueue()
        resolving = job_queue.enqueue_pending("a", _settings())
        queued = job_queue.enqueue("b", _resolution("b"), _settings())

        dispatched = job_queue.dispatch_next(_starter_returning(TranscriptionJob()))

        assert dispatched is queued
        assert queued.state == QueueItemState.PROCESSING
        assert resolving.state == QueueItemState.RESOLVING
        assert job_queue.resolving == [resolving]

    def test_can_be_added_while_another_item_is_processing(self):
        job_queue = TranscriptionJobQueue()
        running = job_queue.enqueue("a", _resolution("a"), _settings())
        job_queue.dispatch_next(_starter_returning(TranscriptionJob()))

        pending = job_queue.enqueue_pending("b", _settings())

        assert running.state == QueueItemState.PROCESSING
        assert job_queue.current is running
        assert pending.state == QueueItemState.RESOLVING
        assert job_queue.resolving == [pending]


# --------------------------------------------------------------------------
# resolve_success
# --------------------------------------------------------------------------
class TestResolveSuccess:
    def test_transitions_resolving_to_queued_and_keeps_resolution(self):
        job_queue = TranscriptionJobQueue()
        item = job_queue.enqueue_pending("a", _settings())
        resolution = _resolution("a")

        job_queue.resolve_success(item, resolution)

        assert item.state == QueueItemState.QUEUED
        assert item.resolution is resolution
        assert job_queue.resolving == []
        assert job_queue.queued == [item]

    def test_does_not_touch_timestamps_or_error_fields(self):
        job_queue = TranscriptionJobQueue()
        item = job_queue.enqueue_pending("a", _settings())

        job_queue.resolve_success(item, _resolution("a"))

        assert item.started_at is None
        assert item.finished_at is None
        assert item.error_message is None
        assert item.resolve_error is None
        assert job_queue.finished == []

    def test_resolved_item_is_dispatched_with_its_resolution(self):
        job_queue = TranscriptionJobQueue()
        item = job_queue.enqueue_pending("a", _settings())
        resolution = _resolution("a")
        job_queue.resolve_success(item, resolution)
        job = TranscriptionJob()
        starter = _starter_returning(job)

        dispatched = job_queue.dispatch_next(starter)

        assert dispatched is item
        assert item.state == QueueItemState.PROCESSING
        assert item.job is job
        assert item.started_at is not None
        starter.assert_called_once_with(item)
        assert starter.call_args.args[0].resolution is resolution

    def test_other_resolving_items_are_not_affected(self):
        job_queue = TranscriptionJobQueue()
        first = job_queue.enqueue_pending("a", _settings())
        second = job_queue.enqueue_pending("b", _settings())

        job_queue.resolve_success(second, _resolution("b"))

        assert first.state == QueueItemState.RESOLVING
        assert first.resolution is None
        assert second.state == QueueItemState.QUEUED
        assert job_queue.resolving == [first]
        assert job_queue.queued == [second]

    def test_queue_order_follows_items_order_not_resolve_order(self):
        """現状の挙動: queued は items の並び順で返る。先に追加した項目が後から
        解決完了しても、後から追加して先に QUEUED になった項目より前に並ぶ。"""
        job_queue = TranscriptionJobQueue()
        first = job_queue.enqueue_pending("a", _settings())
        second = job_queue.enqueue_pending("b", _settings())

        job_queue.resolve_success(second, _resolution("b"))
        job_queue.resolve_success(first, _resolution("a"))

        assert job_queue.queued == [first, second]

        dispatched = job_queue.dispatch_next(_starter_returning(TranscriptionJob()))
        assert dispatched is first


# --------------------------------------------------------------------------
# resolve_failed
# --------------------------------------------------------------------------
class TestResolveFailed:
    def test_transitions_resolving_to_failed_and_keeps_error(self):
        job_queue = TranscriptionJobQueue()
        item = job_queue.enqueue_pending("a", _settings())
        error = RuntimeError("download failed: 403")

        job_queue.resolve_failed(item, error)

        assert item.state == QueueItemState.FAILED
        assert item.resolve_error is error
        assert item.error_message == "download failed: 403"
        assert item.finished_at is not None
        assert item.resolution is None
        assert item.started_at is None
        assert item.job is None

    def test_error_message_is_str_of_exception_even_when_message_is_empty(self):
        job_queue = TranscriptionJobQueue()
        item = job_queue.enqueue_pending("a", _settings())

        job_queue.resolve_failed(item, ValueError())

        assert item.error_message == ""
        assert isinstance(item.resolve_error, ValueError)

    def test_failed_item_appears_in_finished_only(self):
        job_queue = TranscriptionJobQueue()
        item = job_queue.enqueue_pending("a", _settings())

        job_queue.resolve_failed(item, RuntimeError("x"))

        assert job_queue.finished == [item]
        assert job_queue.resolving == []
        assert job_queue.queued == []
        assert job_queue.current is None

    def test_failed_item_is_never_dispatched(self):
        job_queue = TranscriptionJobQueue()
        item = job_queue.enqueue_pending("a", _settings())
        job_queue.resolve_failed(item, RuntimeError("x"))
        starter = MagicMock()

        dispatched = job_queue.dispatch_next(starter)

        assert dispatched is None
        starter.assert_not_called()
        assert item.state == QueueItemState.FAILED

    def test_does_not_affect_other_resolving_or_queued_items(self):
        job_queue = TranscriptionJobQueue()
        failing = job_queue.enqueue_pending("a", _settings())
        other_resolving = job_queue.enqueue_pending("b", _settings())
        queued = job_queue.enqueue("c", _resolution("c"), _settings())

        job_queue.resolve_failed(failing, RuntimeError("x"))

        assert other_resolving.state == QueueItemState.RESOLVING
        assert other_resolving.error_message is None
        assert queued.state == QueueItemState.QUEUED
        assert queued.error_message is None
        assert job_queue.resolving == [other_resolving]
        assert job_queue.queued == [queued]
        assert job_queue.finished == [failing]

    def test_queue_progresses_normally_after_failure(self):
        job_queue = TranscriptionJobQueue()
        failing = job_queue.enqueue_pending("a", _settings())
        later = job_queue.enqueue_pending("b", _settings())

        job_queue.resolve_failed(failing, RuntimeError("x"))
        job_queue.resolve_success(later, _resolution("b"))
        dispatched = job_queue.dispatch_next(_starter_returning(TranscriptionJob()))
        job_queue.mark_done(dispatched, output_file="output/b.txt", gdrive_url=None)

        assert dispatched is later
        assert failing.state == QueueItemState.FAILED
        assert later.state == QueueItemState.DONE
        assert job_queue.finished == [failing, later]

    def test_does_not_disturb_currently_processing_item(self):
        job_queue = TranscriptionJobQueue()
        running = job_queue.enqueue("a", _resolution("a"), _settings())
        job_queue.dispatch_next(_starter_returning(TranscriptionJob()))
        pending = job_queue.enqueue_pending("b", _settings())

        job_queue.resolve_failed(pending, RuntimeError("x"))

        assert job_queue.current is running
        assert running.state == QueueItemState.PROCESSING
        assert job_queue.finished == [pending]

    def test_failed_state_equals_its_string_value(self):
        """`==` 比較(str, Enum)で FAILED と判定できること(tc-ops #548 の前提)。"""
        job_queue = TranscriptionJobQueue()
        item = job_queue.enqueue_pending("a", _settings())

        job_queue.resolve_failed(item, RuntimeError("x"))

        assert item.state == "failed"


# --------------------------------------------------------------------------
# segments_to_srt
# --------------------------------------------------------------------------
class TestSegmentsToSrt:
    def test_empty_list_returns_empty_string(self):
        assert segments_to_srt([]) == ""

    def test_single_segment(self):
        srt = segments_to_srt([_seg(0.0, 1.5, "こんにちは")])

        assert srt == "1\n00:00:00,000 --> 00:00:01,500\nこんにちは\n"

    def test_multiple_segments_are_numbered_and_separated_by_blank_line(self):
        srt = segments_to_srt(
            [
                _seg(0.0, 1.0, "one"),
                _seg(1.0, 2.5, "two"),
                _seg(2.5, 3.0, "three"),
            ]
        )

        assert srt == (
            "1\n00:00:00,000 --> 00:00:01,000\none\n"
            "\n"
            "2\n00:00:01,000 --> 00:00:02,500\ntwo\n"
            "\n"
            "3\n00:00:02,500 --> 00:00:03,000\nthree\n"
        )

    def test_numbering_starts_at_one_regardless_of_segment_times(self):
        srt = segments_to_srt([_seg(100.0, 101.0, "x"), _seg(5.0, 6.0, "y")])

        blocks = srt.split("\n\n")
        assert blocks[0].splitlines()[0] == "1"
        assert blocks[1].splitlines()[0] == "2"

    def test_time_over_one_hour(self):
        srt = segments_to_srt([_seg(3725.5, 7199.999, "long")])

        assert srt == "1\n01:02:05,500 --> 01:59:59,999\nlong\n"

    def test_hours_are_not_capped_at_two_digits(self):
        srt = segments_to_srt([_seg(360000.0, 360001.0, "x")])

        assert srt.splitlines()[1] == "100:00:00,000 --> 100:00:01,000"

    def test_exact_hour_boundary(self):
        srt = segments_to_srt([_seg(3599.999, 3600.0, "x")])

        assert srt.splitlines()[1] == "00:59:59,999 --> 01:00:00,000"

    def test_milliseconds_are_rounded_to_nearest(self):
        srt = segments_to_srt([_seg(1.0004, 1.0006, "x")])

        assert srt.splitlines()[1] == "00:00:01,000 --> 00:00:01,001"

    def test_milliseconds_rounding_can_carry_into_seconds(self):
        srt = segments_to_srt([_seg(0.9996, 59.9996, "x")])

        assert srt.splitlines()[1] == "00:00:01,000 --> 00:01:00,000"

    def test_milliseconds_half_uses_round_half_to_even(self):
        """現状の挙動: Python の round() による銀行丸め(0.5ms 単位は偶数側へ)。"""
        srt = segments_to_srt([_seg(0.0005, 0.0015, "x")])

        assert srt.splitlines()[1] == "00:00:00,000 --> 00:00:00,002"

    def test_negative_time_is_clamped_to_zero(self):
        srt = segments_to_srt([_seg(-1.5, -0.1, "x")])

        assert srt.splitlines()[1] == "00:00:00,000 --> 00:00:00,000"

    def test_text_is_not_stripped(self):
        """現状の挙動: テキストの前後空白はそのまま出力される(trim しない)。"""
        srt = segments_to_srt([_seg(0.0, 1.0, "  padded  ")])

        assert srt.splitlines()[2] == "  padded  "

    def test_empty_text_still_emits_block(self):
        srt = segments_to_srt([_seg(0.0, 1.0, "")])

        assert srt == "1\n00:00:00,000 --> 00:00:01,000\n\n"

    def test_multiline_text_is_kept_verbatim(self):
        srt = segments_to_srt([_seg(0.0, 1.0, "line1\nline2")])

        assert srt == "1\n00:00:00,000 --> 00:00:01,000\nline1\nline2\n"

    def test_integer_seconds_are_accepted(self):
        srt = segments_to_srt([_seg(1, 2, "x")])

        assert srt.splitlines()[1] == "00:00:01,000 --> 00:00:02,000"


# --------------------------------------------------------------------------
# drain_progress
# --------------------------------------------------------------------------
class TestDrainProgress:
    def test_empty_queue_returns_empty_list(self):
        job = TranscriptionJob()

        assert drain_progress(job) == []

    def test_returns_single_message_and_empties_queue(self):
        job = TranscriptionJob()
        job.progress_queue.put("読み込み中")

        assert drain_progress(job) == ["読み込み中"]
        assert job.progress_queue.empty()

    def test_returns_multiple_messages_in_fifo_order(self):
        job = TranscriptionJob()
        for message in ["a", "b", "c"]:
            job.progress_queue.put(message)

        assert drain_progress(job) == ["a", "b", "c"]
        assert job.progress_queue.empty()

    def test_second_call_returns_only_messages_added_since(self):
        job = TranscriptionJob()
        job.progress_queue.put("first")
        drain_progress(job)
        job.progress_queue.put("second")

        assert drain_progress(job) == ["second"]
        assert drain_progress(job) == []

    def test_does_not_block_on_empty_queue(self):
        """ノンブロッキング: 空のキューでも即座に戻る(タイムアウト付きスレッドで確認)。"""
        job = TranscriptionJob()
        results = []

        thread = threading.Thread(target=lambda: results.append(drain_progress(job)), daemon=True)
        thread.start()
        thread.join(timeout=_JOIN_TIMEOUT_SEC)

        assert not thread.is_alive()
        assert results == [[]]

    def test_does_not_modify_queue_item_log(self):
        """実装は取り出したメッセージを返すだけで、QueueItem.log へは書き込まない
        (log への追記は呼び出し側の責務)。"""
        job_queue = TranscriptionJobQueue()
        item = job_queue.enqueue("a", _resolution("a"), _settings())
        job = TranscriptionJob()
        item.job = job
        job.progress_queue.put("msg")

        messages = drain_progress(job)

        assert messages == ["msg"]
        assert item.log == []

    def test_returned_messages_can_be_appended_to_item_log_by_caller(self):
        job_queue = TranscriptionJobQueue()
        item = job_queue.enqueue("a", _resolution("a"), _settings())
        item.job = TranscriptionJob()
        item.job.progress_queue.put("m1")
        item.job.progress_queue.put("m2")

        item.log.extend(drain_progress(item.job))

        assert item.log == ["m1", "m2"]


# --------------------------------------------------------------------------
# start_transcription_job
# --------------------------------------------------------------------------
class _FakeTranscriber:
    """`UnifiedTranscriber.transcribe` の代わり。呼び出し引数を記録する。"""

    def __init__(self, result=None, error=None, progress_messages=()):
        self._result = result
        self._error = error
        self._progress_messages = list(progress_messages)
        self.calls = []
        self.thread_ident = None

    def transcribe(self, audio_path, progress_callback=None, **kwargs):
        self.thread_ident = threading.get_ident()
        self.calls.append((audio_path, progress_callback, kwargs))
        for message in self._progress_messages:
            progress_callback(message)
        if self._error is not None:
            raise self._error
        return self._result


def _wait(job: TranscriptionJob) -> None:
    assert job.thread is not None
    job.thread.join(timeout=_JOIN_TIMEOUT_SEC)
    assert not job.thread.is_alive(), "ジョブのスレッドがタイムアウト内に終了しなかった"


class TestStartTranscriptionJob:
    def test_success_sets_done_and_keeps_result(self):
        sentinel = object()
        transcriber = _FakeTranscriber(result=sentinel)

        job = start_transcription_job(transcriber, "audio.wav")
        _wait(job)

        assert job.done is True
        assert job.result is sentinel
        assert job.error is None

    def test_returns_transcription_job_with_daemon_thread(self):
        transcriber = _FakeTranscriber(result="r")

        job = start_transcription_job(transcriber, "audio.wav")
        _wait(job)

        assert isinstance(job, TranscriptionJob)
        assert isinstance(job.thread, threading.Thread)
        assert job.thread.daemon is True

    def test_transcribe_runs_in_background_thread(self):
        transcriber = _FakeTranscriber(result="r")

        job = start_transcription_job(transcriber, "audio.wav")
        _wait(job)

        assert transcriber.thread_ident is not None
        assert transcriber.thread_ident != threading.get_ident()
        assert transcriber.thread_ident == job.thread.ident

    def test_passes_audio_path_kwargs_and_progress_callback(self):
        transcriber = _FakeTranscriber(result="r")

        job = start_transcription_job(
            transcriber, "/tmp/a.wav", language="ja", include_timestamps=True
        )
        _wait(job)

        assert len(transcriber.calls) == 1
        audio_path, progress_callback, kwargs = transcriber.calls[0]
        assert audio_path == "/tmp/a.wav"
        assert callable(progress_callback)
        assert kwargs == {"language": "ja", "include_timestamps": True}

    def test_progress_messages_reach_progress_queue_in_order(self):
        transcriber = _FakeTranscriber(result="r", progress_messages=["p1", "p2", "p3"])

        job = start_transcription_job(transcriber, "audio.wav")
        _wait(job)

        assert drain_progress(job) == ["p1", "p2", "p3"]

    def test_exception_is_kept_in_error_and_done_is_set(self):
        error = RuntimeError("CUDA error")
        transcriber = _FakeTranscriber(error=error)

        job = start_transcription_job(transcriber, "audio.wav")
        _wait(job)

        assert job.done is True
        assert job.error is error
        assert job.result is None

    def test_progress_before_exception_is_still_available(self):
        transcriber = _FakeTranscriber(error=ValueError("bad"), progress_messages=["before"])

        job = start_transcription_job(transcriber, "audio.wav")
        _wait(job)

        assert isinstance(job.error, ValueError)
        assert drain_progress(job) == ["before"]

    def test_base_exception_is_also_captured(self):
        """現状の挙動: `except BaseException` のため Exception 以外(SystemExit 等)も
        スレッド外へ漏れず job.error に保持される。"""
        transcriber = _FakeTranscriber(error=SystemExit(3))

        job = start_transcription_job(transcriber, "audio.wav")
        _wait(job)

        assert job.done is True
        assert isinstance(job.error, SystemExit)
        assert job.result is None

    def test_none_result_is_kept_as_none_with_done_true(self):
        transcriber = _FakeTranscriber(result=None)

        job = start_transcription_job(transcriber, "audio.wav")
        _wait(job)

        assert job.done is True
        assert job.result is None
        assert job.error is None

    def test_new_job_has_initial_state_before_completion(self):
        job = TranscriptionJob()

        assert job.thread is None
        assert job.result is None
        assert job.error is None
        assert job.done is False
        assert job.progress_queue.empty()

    def test_job_can_be_used_as_starter_result_for_dispatch(self):
        """dispatch_next の starter として start_transcription_job をラップした場合の統合確認。"""
        sentinel = object()
        transcriber = _FakeTranscriber(result=sentinel)
        job_queue = TranscriptionJobQueue()
        item = job_queue.enqueue_pending("a", _settings())
        job_queue.resolve_success(item, _resolution("a"))

        dispatched = job_queue.dispatch_next(
            lambda queue_item: start_transcription_job(transcriber, "audio.wav")
        )
        _wait(dispatched.job)

        assert dispatched is item
        assert item.state == QueueItemState.PROCESSING
        assert item.job.done is True
        assert item.job.result is sentinel


@pytest.mark.parametrize("repeat", range(3))
def test_threaded_job_is_stable_across_repeats(repeat):
    """スレッドを使うジョブを繰り返し実行しても結果が揺れないこと(不安定さの検出用)。"""
    transcriber = _FakeTranscriber(result=repeat, progress_messages=["x", "y"])

    job = start_transcription_job(transcriber, "audio.wav")
    _wait(job)

    assert job.done is True
    assert job.result == repeat
    assert drain_progress(job) == ["x", "y"]
