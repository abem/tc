"""
Tests for webui._format_finished_item_label() / _sorted_finished_items()
(2026-08-05、WebUIキュー完了済み一覧の表示順・識別性改善)。

`webui.py`自体はStreamlit依存のため直接ユニットテスト対象に含めない(既存方針を踏襲)。
完了済み一覧の表示文言組み立て・ソートロジック(いずれも`QueueItem`/`TranscriptionJobQueue`を
直接操作するだけの純粋関数)を検証する。

対象の背景: 是正前は投入`item_id`の降順で表示していたため、「投入は後だが確定は先」の項目が
「投入は先だが確定は後」の項目より上に表示され、実際に最後に確定した結果が一番上に来るとは
限らなかった(WebUIキュー投入UX網羅調査パターン1bで確認)。本テストは、確定時刻(`finished_at`)の
降順ソートと、`item_id`・確定時刻を含む見出し文言によって、この問題が解消されることを固定化する。
"""

from unittest.mock import MagicMock

from webui import _format_finished_item_label, _format_time, _sorted_finished_items
from core.webui_workflow import QueueItemState, TranscriptionJobQueue


def _settings():
    return {"model": "Qwen/Qwen3-ASR-1.7B", "device": "cpu", "include_timestamps": False}


class TestFormatTime:
    def test_formats_epoch_as_hhmmss(self):
        # 2026-01-01 00:00:00 UTC 相当の適当なepoch値ではなくローカル時刻依存を避けるため、
        # フォーマット形式(コロン区切り3要素)のみを検証する。
        formatted = _format_time(1750000000.0)
        assert formatted.count(":") == 2

    def test_returns_placeholder_for_none(self):
        assert _format_time(None) == "-"


class TestFormatFinishedItemLabel:
    def test_label_includes_item_id_for_identifiability(self):
        """同一ラベル(同一URL等)の複数項目でも、見出しにitem_idが含まれ区別できることを検証する
        (識別不能問題の是正)。"""
        job_queue = TranscriptionJobQueue()
        item_a = job_queue.enqueue("https://example.com/same", resolution=MagicMock(), settings=_settings())
        item_b = job_queue.enqueue("https://example.com/same", resolution=MagicMock(), settings=_settings())
        job_queue.dispatch_next(lambda item: MagicMock())
        job_queue.mark_done(item_a, output_file="a.txt", gdrive_url=None)

        label = _format_finished_item_label(item_a)
        assert f"#{item_a.item_id}" in label
        assert label != _format_finished_item_label(item_b) if item_b.item_id != item_a.item_id else True

    def test_label_includes_status_and_finished_time(self):
        job_queue = TranscriptionJobQueue()
        item = job_queue.enqueue("https://example.com/x", resolution=MagicMock(), settings=_settings())
        job_queue.dispatch_next(lambda i: MagicMock())
        job_queue.mark_failed(item, error_message="boom")

        label = _format_finished_item_label(item)
        assert "[失敗]" in label
        assert f"#{item.item_id}" in label
        assert "確定" in label


class TestSortedFinishedItems:
    def test_sorts_by_finished_at_descending_not_by_item_id(self):
        """投入が後の項目が先に確定した場合(tc-ops #440是正3以降の網羅調査パターン1b相当)、
        確定時刻の新しい順(item_id降順ではない)で並ぶことを検証する。"""
        job_queue = TranscriptionJobQueue()
        item_first_submitted = job_queue.enqueue(
            "https://example.com/first", resolution=MagicMock(), settings=_settings()
        )
        item_second_submitted = job_queue.enqueue(
            "https://example.com/second", resolution=MagicMock(), settings=_settings()
        )

        # item_first_submitted(投入順1番目)が処理中のまま、item_second_submitted(2番目)を
        # 先に失敗確定させる(投入順と確定順が逆転するケース)。
        job_queue.dispatch_next(lambda i: MagicMock())
        assert job_queue.current is item_first_submitted
        job_queue.mark_failed(item_second_submitted, error_message="submitted later, failed first")

        import time as _time
        _time.sleep(0.01)
        job_queue.mark_done(item_first_submitted, output_file="first.txt", gdrive_url=None)

        finished = _sorted_finished_items(job_queue)
        assert finished[0] is item_first_submitted  # 投入は先だが確定は後 -> 新しい順で先頭
        assert finished[1] is item_second_submitted

    def test_sorts_all_done_items_by_natural_completion_order_when_submitted_in_order(self):
        job_queue = TranscriptionJobQueue()
        item1 = job_queue.enqueue("https://example.com/a", resolution=MagicMock(), settings=_settings())
        job_queue.dispatch_next(lambda i: MagicMock())
        job_queue.mark_done(item1, output_file="a.txt", gdrive_url=None)

        import time as _time
        _time.sleep(0.01)

        item2 = job_queue.enqueue("https://example.com/b", resolution=MagicMock(), settings=_settings())
        job_queue.dispatch_next(lambda i: MagicMock())
        job_queue.mark_done(item2, output_file="b.txt", gdrive_url=None)

        finished = _sorted_finished_items(job_queue)
        assert finished[0] is item2
        assert finished[1] is item1
        assert finished[0].state is QueueItemState.DONE
