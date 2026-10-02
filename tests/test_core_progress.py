"""core/progress.py と WebUI進捗バー関連(core/webui_workflow.py)のテスト。"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import numpy as np

from core.progress import ProgressMessage, emit_progress, parse_ytdlp_progress
from core.webui_workflow import (
    QueueItem,
    QueueItemState,
    TranscriptionJobQueue,
    apply_progress,
    estimate_remaining,
    format_elapsed,
)


class TestProgressMessage:
    def test_is_a_plain_str_for_existing_callbacks(self):
        message = ProgressMessage("文字起こし中 1/3", 1 / 3)

        assert isinstance(message, str)
        assert message == "文字起こし中 1/3"
        assert message.fraction == 1 / 3

    def test_fraction_is_clamped_and_optional(self):
        assert ProgressMessage("x", 1.7).fraction == 1.0
        assert ProgressMessage("x", -0.2).fraction == 0.0
        assert ProgressMessage("x").fraction is None

    def test_emit_progress_swallows_callback_errors(self):
        def boom(_message):
            raise RuntimeError("UI側の不具合")

        emit_progress(boom, "x", 0.5)  # 例外が伝播しないこと
        emit_progress(None, "x", 0.5)


class TestParseYtdlpProgress:
    def test_parses_percent_and_eta(self):
        line = "[download]  12.5% of ~ 300.00MiB at  2.00MiB/s ETA 02:31 (frag 5/40)"

        assert parse_ytdlp_progress(line) == (0.125, "02:31")

    def test_percent_without_eta(self):
        assert parse_ytdlp_progress("[download] 100% of 1.00MiB in 00:00:01") == (1.0, None)

    def test_non_progress_line_is_none(self):
        assert parse_ytdlp_progress("[ExtractAudio] Destination: a.wav") is None
        assert parse_ytdlp_progress("") is None


class TestApplyProgress:
    def _item(self):
        return QueueItem(label="x", settings={})

    def test_progress_message_updates_item_and_is_consumed(self):
        item = self._item()

        consumed = apply_progress(item, ProgressMessage("ダウンロード中 40%", 0.4))

        assert consumed is True
        assert item.progress == 0.4
        assert item.progress_text == "ダウンロード中 40%"

    def test_message_without_fraction_clears_bar_but_shows_text(self):
        item = self._item()
        apply_progress(item, ProgressMessage("ダウンロード中 100%", 1.0))

        apply_progress(item, ProgressMessage("音声をwavに変換中"))

        assert item.progress is None
        assert item.progress_text == "音声をwavに変換中"

    def test_plain_message_is_not_consumed(self):
        item = self._item()

        assert apply_progress(item, "YouTube URLを検出") is False
        assert item.progress is None and item.progress_text == ""

    def test_progress_is_reset_between_stages(self):
        """解決(ダウンロード)段階の100%が、文字起こし段階の開始時に残らない。"""
        queue = TranscriptionJobQueue()
        item = queue.enqueue_pending("x", {})
        apply_progress(item, ProgressMessage("ダウンロード中 100%", 1.0))

        queue.resolve_success(item, resolution=MagicMock())
        assert (item.progress, item.progress_text) == (None, "")

        apply_progress(item, ProgressMessage("stale", 0.9))
        queue.dispatch_next(lambda _item: MagicMock())
        assert item.state == QueueItemState.PROCESSING
        assert (item.progress, item.progress_text) == (None, "")


class TestTimeFormatting:
    def test_format_elapsed(self):
        assert format_elapsed(0) == "0:00"
        assert format_elapsed(75) == "1:15"
        assert format_elapsed(3725) == "1:02:05"
        assert format_elapsed(-5) == "0:00"

    def test_estimate_remaining(self):
        assert estimate_remaining(100.0, 0.5) == 100.0
        assert estimate_remaining(30.0, 0.25) == 90.0

    def test_estimate_is_unavailable_when_unknown_or_too_early(self):
        assert estimate_remaining(10.0, None) is None
        assert estimate_remaining(1.0, 0.01) is None


class TestQwenLongAudioProgress:
    """長音声(分割処理)でチャンクごとに進捗が通知される。"""

    def _engine(self):
        from core.config import TranscriptionConfig
        from core.transcription_interface import Qwen3ASREngine

        engine = Qwen3ASREngine(TranscriptionConfig(model="Qwen/Qwen3-ASR-1.7B", language="en", device="cpu"))
        engine._model = MagicMock()
        engine._model.transcribe.return_value = [SimpleNamespace(text="hello world", language="English")]
        return engine

    def test_reports_each_chunk(self):
        engine = self._engine()
        sr = 16000
        audio = np.zeros(engine.CHUNK_THRESHOLD_SEC * sr * 3, dtype=np.float32)  # 3チャンク分
        messages = []

        with patch("librosa.load", return_value=(audio, sr)):
            engine._transcribe_long_audio(
                "dummy.wav", duration=engine.CHUNK_THRESHOLD_SEC * 3, language="English", context="",
                progress_callback=messages.append,
            )

        assert [m.fraction for m in messages] == [0.0, 1 / 3, 2 / 3, 1.0]
        assert "3チャンク" in messages[0]
        assert "3/3" in messages[-1]

    def test_works_without_callback(self):
        engine = self._engine()
        sr = 16000
        audio = np.zeros(engine.CHUNK_THRESHOLD_SEC * sr, dtype=np.float32)

        with patch("librosa.load", return_value=(audio, sr)):
            text, *_ = engine._transcribe_long_audio(
                "dummy.wav", duration=engine.CHUNK_THRESHOLD_SEC, language="English", context=""
            )

        assert "hello" in text


class TestThrottled:
    def test_prints_progress_once_per_step_and_all_plain_messages(self):
        from core.progress import throttled

        printed = []
        status = throttled(printed.append, steps=10)

        status("YouTube URLを検出")
        for percent in range(0, 101):  # 1%刻みで届く
            status(ProgressMessage(f"ダウンロード中 {percent}%", percent / 100))
        status(ProgressMessage("音声をwavに変換中"))  # 率なし → 常に出す

        assert printed[0] == "YouTube URLを検出"
        assert printed[-1] == "音声をwavに変換中"
        progress_lines = printed[1:-1]
        assert len(progress_lines) == 11  # 0%,10%,...,100%
        assert progress_lines[0] == "ダウンロード中 0%" and progress_lines[-1] == "ダウンロード中 100%"


class TestUnifiedTranscriberForwardsCallback:
    def test_progress_callback_reaches_engine(self):
        from unittest.mock import MagicMock

        from core.transcription_interface import UnifiedTranscriber

        transcriber = UnifiedTranscriber.__new__(UnifiedTranscriber)
        transcriber.transcription_engine = MagicMock()
        callback = MagicMock()

        transcriber._transcribe_standard("a.wav", callback)

        _, kwargs = transcriber.transcription_engine.transcribe.call_args
        assert kwargs["progress_callback"] is callback
