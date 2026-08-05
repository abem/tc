"""
Tests for core.webui_workflow.TranscriptionJobQueue / QueueItem
(2026-08-05、tc-ops #440: WebUI文字起こしジョブのキュー処理化)。

対象: 複数ジョブの逐次自動処理(並列実行なし)・状態遷移(QUEUED/PROCESSING/DONE/FAILED)・
各項目が専有する`resolution`によるクリーンアップの他項目非干渉。
`start_transcription_job()`(実スレッド起動)はモック(`starter`)に差し替え、Streamlit非依存で検証する。
"""

from unittest.mock import MagicMock

from core.webui_workflow import QueueItem, QueueItemState, TranscriptionJob, TranscriptionJobQueue


def _resolution(name: str):
    return MagicMock(name=name)


def _settings():
    return {"model": "Qwen/Qwen3-ASR-1.7B", "device": "cpu", "include_timestamps": False}


def _starter_returning(job: TranscriptionJob):
    return MagicMock(side_effect=lambda item: job)


class TestEnqueueAndDispatch:
    def test_enqueue_adds_item_in_queued_state(self):
        job_queue = TranscriptionJobQueue()
        item = job_queue.enqueue("https://example.com/a", _resolution("a"), _settings())

        assert item.state is QueueItemState.QUEUED
        assert job_queue.queued == [item]
        assert job_queue.current is None

    def test_dispatch_next_starts_item_when_idle(self):
        job_queue = TranscriptionJobQueue()
        item = job_queue.enqueue("a", _resolution("a"), _settings())
        job = TranscriptionJob()
        starter = _starter_returning(job)

        dispatched = job_queue.dispatch_next(starter)

        assert dispatched is item
        assert item.state is QueueItemState.PROCESSING
        assert item.job is job
        assert item.started_at is not None
        starter.assert_called_once_with(item)

    def test_additional_enqueue_does_not_disturb_processing_item(self):
        job_queue = TranscriptionJobQueue()
        first = job_queue.enqueue("a", _resolution("a"), _settings())
        job_queue.dispatch_next(_starter_returning(TranscriptionJob()))
        assert first.state is QueueItemState.PROCESSING

        second = job_queue.enqueue("b", _resolution("b"), _settings())

        assert first.state is QueueItemState.PROCESSING
        assert second.state is QueueItemState.QUEUED
        assert job_queue.queued == [second]

    def test_dispatch_next_is_noop_while_current_item_processing(self):
        job_queue = TranscriptionJobQueue()
        job_queue.enqueue("a", _resolution("a"), _settings())
        job_queue.dispatch_next(_starter_returning(TranscriptionJob()))
        job_queue.enqueue("b", _resolution("b"), _settings())

        second_starter = MagicMock()
        result = job_queue.dispatch_next(second_starter)

        assert result is None
        second_starter.assert_not_called()
        assert len(job_queue.queued) == 1

    def test_dispatch_next_starts_next_item_after_current_marked_done(self):
        job_queue = TranscriptionJobQueue()
        first = job_queue.enqueue("a", _resolution("a"), _settings())
        job_queue.dispatch_next(_starter_returning(TranscriptionJob()))
        second = job_queue.enqueue("b", _resolution("b"), _settings())

        job_queue.mark_done(first, output_file="output/a.txt", gdrive_url=None)
        next_job = TranscriptionJob()
        dispatched = job_queue.dispatch_next(_starter_returning(next_job))

        assert first.state is QueueItemState.DONE
        assert first.output_file == "output/a.txt"
        assert first.finished_at is not None
        assert dispatched is second
        assert second.state is QueueItemState.PROCESSING
        assert job_queue.finished == [first]


class TestFailureHandling:
    def test_mark_failed_does_not_block_subsequent_dispatch(self):
        job_queue = TranscriptionJobQueue()
        first = job_queue.enqueue("a", _resolution("a"), _settings())
        job_queue.dispatch_next(_starter_returning(TranscriptionJob()))
        second = job_queue.enqueue("b", _resolution("b"), _settings())

        job_queue.mark_failed(first, error_message="boom")

        assert first.state is QueueItemState.FAILED
        assert first.error_message == "boom"
        assert job_queue.current is None

        dispatched = job_queue.dispatch_next(_starter_returning(TranscriptionJob()))
        assert dispatched is second
        assert second.state is QueueItemState.PROCESSING


class TestResolutionIsolation:
    def test_each_item_holds_its_own_resolution(self):
        job_queue = TranscriptionJobQueue()
        res_a = _resolution("a")
        res_b = _resolution("b")
        item_a = job_queue.enqueue("a", res_a, _settings())
        item_b = job_queue.enqueue("b", res_b, _settings())

        assert item_a.resolution is res_a
        assert item_b.resolution is res_b
        assert item_a.resolution is not item_b.resolution

    def test_settings_dict_is_copied_not_shared(self):
        job_queue = TranscriptionJobQueue()
        settings = _settings()
        item = job_queue.enqueue("a", _resolution("a"), settings)

        settings["model"] = "changed-after-enqueue"

        assert item.settings["model"] != "changed-after-enqueue"
