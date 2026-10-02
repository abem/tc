"""
WhisperTranscriptionEngine のテキスト整形(特性化テスト)。

対象: _parse_timestamped_text / _add_timestamps_to_text /
_ensure_timestamps_at_line_start / _create_chunks。
Phase 5 Task 5.4 のモジュール分割前に「現在の出力」を固定する目的で追加した
(既存コードの特性化のため、追加時点から pass する)。
"""

import numpy as np
import pytest

from core.config import TranscriptionConfig
from core.utils import DEFAULT_AUDIO_DURATION_SEC


@pytest.fixture
def engine():
    from core.transcription_interface import WhisperTranscriptionEngine

    return WhisperTranscriptionEngine(
        TranscriptionConfig(model="openai/whisper-small", language="ja", device="cpu")
    )


class TestParseTimestampedText:
    def test_multiple_timestamps_become_30s_segments(self, engine):
        segs = engine._parse_timestamped_text("[00:00] こんにちは\n[00:30] 世界\n[01:05] 終わり")
        assert [(s.start, s.end, s.text) for s in segs] == [
            (0, 30, "こんにちは"),
            (30, 60, "世界"),
            (65, 95, "終わり"),
        ]
        assert all(s.language == "ja" for s in segs)

    def test_no_timestamp_makes_single_segment_with_fallback_duration(self, engine):
        segs = engine._parse_timestamped_text("  タイムスタンプなし  ")
        assert len(segs) == 1
        assert segs[0].start == 0.0
        assert segs[0].end == DEFAULT_AUDIO_DURATION_SEC
        assert segs[0].text == "タイムスタンプなし"

    def test_empty_or_blank_returns_no_segments(self, engine):
        assert engine._parse_timestamped_text("") == []
        assert engine._parse_timestamped_text("   \n ") == []

    def test_text_before_first_timestamp_is_dropped(self, engine):
        segs = engine._parse_timestamped_text("前置き[00:10] 本文")
        assert [(s.start, s.text) for s in segs] == [(10, "本文")]


class TestAddTimestampsToText:
    @pytest.mark.parametrize(
        "start_seconds, expected_prefix",
        [(0, "[00:00]"), (59, "[00:59]"), (60, "[01:00]"), (125, "[02:05]"), (3600, "[60:00]")],
    )
    def test_timestamp_prefix_format(self, engine, start_seconds, expected_prefix):
        assert engine._add_timestamps_to_text("abc", start_seconds) == f"{expected_prefix} abc"

    def test_text_is_stripped(self, engine):
        assert engine._add_timestamps_to_text("  hello \n", 30) == "[00:30] hello"

    @pytest.mark.parametrize("blank", ["", "   ", "\n\t"])
    def test_blank_text_returns_empty(self, engine, blank):
        assert engine._add_timestamps_to_text(blank, 10) == ""


class TestEnsureTimestampsAtLineStart:
    def test_line_with_leading_timestamp_unchanged(self, engine):
        assert engine._ensure_timestamps_at_line_start("[00:00] a\n[00:30] b") == "[00:00] a\n[00:30] b"

    def test_timestamp_in_middle_is_moved_to_front(self, engine):
        assert engine._ensure_timestamps_at_line_start("abc [00:30] def") == "[00:30] abc  def"

    def test_blank_lines_removed_and_lines_stripped(self, engine):
        assert engine._ensure_timestamps_at_line_start("  [00:00] a  \n\n   \n[00:30] b") == "[00:00] a\n[00:30] b"

    def test_line_without_timestamp_kept_as_is(self, engine):
        assert engine._ensure_timestamps_at_line_start("no stamp") == "no stamp"

    def test_line_starting_with_bracket_is_not_reordered(self, engine):
        assert engine._ensure_timestamps_at_line_start("[memo] x [00:10]") == "[memo] x [00:10]"

    def test_empty_text(self, engine):
        assert engine._ensure_timestamps_at_line_start("") == ""


class TestCreateChunks:
    def test_splits_into_chunk_size_pieces_with_remainder(self, engine):
        chunks = engine._create_chunks(np.arange(10), 4)
        assert [c.tolist() for c in chunks] == [[0, 1, 2, 3], [4, 5, 6, 7], [8, 9]]

    def test_exact_multiple_has_no_empty_tail(self, engine):
        chunks = engine._create_chunks(np.arange(8), 4)
        assert [len(c) for c in chunks] == [4, 4]

    def test_shorter_than_chunk_size_is_single_chunk(self, engine):
        chunks = engine._create_chunks(np.arange(3), 100)
        assert [c.tolist() for c in chunks] == [[0, 1, 2]]

    def test_empty_audio_returns_no_chunks(self, engine):
        assert engine._create_chunks(np.array([]), 4) == []
