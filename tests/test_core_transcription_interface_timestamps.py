"""
Tests for core.transcription_interface.Qwen3ASREngine のタイムスタンプ対応
(2026-08-03、config.include_timestamps オプトイン機能)。

対象: ForcedAligner(qwen_asr同梱のQwen3ForcedAligner)を用いた文節単位の
タイムスタンプ付与。既存の出力形式(config.include_timestamps=False、既定)
を壊さないことと、アライナーのロード/実行失敗時に例外を投げず通常出力へ
フォールバックすることを重点的に検証する。
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import numpy as np
import pytest


def _make_engine(include_timestamps=False):
    from core.config import TranscriptionConfig
    from core.transcription_interface import Qwen3ASREngine

    config = TranscriptionConfig(
        model="Qwen/Qwen3-ASR-1.7B",
        language="ja",
        device="cpu",
        include_timestamps=include_timestamps,
    )
    return Qwen3ASREngine(config)


def _item(text, start, end):
    return SimpleNamespace(text=text, start_time=start, end_time=end)


class TestCoreCharCount:
    def test_counts_letters_and_numbers_only(self):
        from core.transcription_interface import Qwen3ASREngine

        assert Qwen3ASREngine._core_char_count("これは、テストです。") == 8  # 句読点2個を除く
        assert Qwen3ASREngine._core_char_count("abc123") == 6
        assert Qwen3ASREngine._core_char_count("、。！？") == 0

    def test_empty_string(self):
        from core.transcription_interface import Qwen3ASREngine

        assert Qwen3ASREngine._core_char_count("") == 0


class TestMatchFragmentsToAlignment:
    def test_basic_matching(self):
        from core.transcription_interface import Qwen3ASREngine

        fragments = ["これは、", "テストです。"]
        # 「これは」(3文字) + 「テストです」(5文字) 相当のアイテム列
        align_items = [
            _item("これ", 0.0, 0.5),
            _item("は", 0.5, 0.7),
            _item("テスト", 0.8, 1.5),
            _item("です", 1.5, 1.9),
        ]
        boundaries = Qwen3ASREngine._match_fragments_to_alignment(fragments, align_items)
        assert len(boundaries) == 2
        # 「これは、」= 3実質文字 -> 「これ」(2)+「は」(1)で消費完了
        assert boundaries[0] == (0.0, 0.7)
        # 「テストです。」= 5実質文字 -> 「テスト」(3)+「です」(2)で消費完了
        assert boundaries[1] == (0.8, 1.9)

    def test_empty_fragment_reuses_previous_end(self):
        from core.transcription_interface import Qwen3ASREngine

        fragments = ["、", "テスト。"]  # 先頭フラグメントは実質文字数0
        align_items = [_item("テスト", 1.0, 2.0)]
        boundaries = Qwen3ASREngine._match_fragments_to_alignment(fragments, align_items)
        assert boundaries[0] == (0.0, 0.0)
        assert boundaries[1] == (1.0, 2.0)

    def test_more_fragments_than_items(self):
        """アイテムを使い切った後のフラグメントは直前の終端を引き継ぐ(クラッシュしない)。"""
        from core.transcription_interface import Qwen3ASREngine

        fragments = ["これは。", "テストです。", "もう一つ。"]
        align_items = [_item("これは", 0.0, 1.0)]
        boundaries = Qwen3ASREngine._match_fragments_to_alignment(fragments, align_items)
        assert len(boundaries) == 3
        assert boundaries[0] == (0.0, 1.0)
        assert boundaries[1] == (1.0, 1.0)
        assert boundaries[2] == (1.0, 1.0)


class TestAlignerLoadFallback:
    def test_load_aligner_failure_does_not_raise(self):
        engine = _make_engine(include_timestamps=True)

        with patch(
            "qwen_asr.inference.qwen3_forced_aligner.Qwen3ForcedAligner.from_pretrained",
            side_effect=RuntimeError("simulated download failure"),
        ):
            ok = engine._load_aligner()

        assert ok is False
        assert engine._aligner_unavailable is True

    def test_align_chunk_returns_empty_list_on_load_failure(self):
        engine = _make_engine(include_timestamps=True)
        engine._aligner_unavailable = True  # ロード失敗済みの状態を模擬

        items = engine._align_chunk("dummy.wav", "テストです。", "Japanese", offset_sec=0.0)
        assert items == []

    def test_align_chunk_returns_empty_list_on_align_exception(self):
        engine = _make_engine(include_timestamps=True)
        engine._aligner = MagicMock()
        engine._aligner.align.side_effect = RuntimeError("simulated inference failure")

        items = engine._align_chunk("dummy.wav", "テストです。", "Japanese", offset_sec=0.0)
        assert items == []


class TestTranscribeTimestampIntegration:
    """transcribe()(短音声経路)でのタイムスタンプ配線を、実モデル・実GPU無しで検証する。"""

    def _run_transcribe(self, engine, asr_text, align_items_or_exception):
        engine._model = MagicMock()
        engine._model.transcribe.return_value = [SimpleNamespace(text=asr_text, language="Japanese")]

        with patch.object(engine, "_load_model", return_value=None), \
             patch.object(engine, "_get_audio_duration", return_value=1.0), \
             patch.object(engine, "validate_audio_file", return_value=True):
            if isinstance(align_items_or_exception, Exception):
                with patch.object(engine, "_align_chunk", side_effect=align_items_or_exception):
                    return engine.transcribe("dummy.wav")
            else:
                with patch.object(engine, "_align_chunk", return_value=align_items_or_exception):
                    return engine.transcribe("dummy.wav")

    def test_include_timestamps_false_keeps_single_segment(self):
        """既定(config.include_timestamps=False、opt-in前のデフォルト挙動)は
        従来どおり全体1セグメントであること(回帰防止)。"""
        engine = _make_engine(include_timestamps=False)
        result = self._run_transcribe(engine, "これはテストです。", [])

        assert len(result.segments) == 1
        assert result.segments[0].text == result.text
        assert result.metadata["timestamps_included"] is False

    def test_include_timestamps_true_builds_multi_segment(self):
        engine = _make_engine(include_timestamps=True)
        align_items = [
            _item("これ", 0.0, 0.3),
            _item("は", 0.3, 0.4),
            _item("テスト", 0.5, 1.0),
            _item("です", 1.0, 1.3),
        ]
        result = self._run_transcribe(engine, "これは、テストです。", align_items)

        assert result.metadata["timestamps_included"] is True
        assert len(result.segments) == 2
        assert result.segments[0].text == "これは、"
        assert result.segments[0].start == 0.0
        assert result.segments[1].text == "テストです。"
        assert result.segments[1].start == 0.5

    def test_include_timestamps_true_falls_back_when_alignment_empty(self):
        """アライナー失敗(_align_chunkが空リストを返す)時は単一セグメントに
        フォールバックし、例外は投げない。"""
        engine = _make_engine(include_timestamps=True)
        result = self._run_transcribe(engine, "これはテストです。", [])

        assert result.metadata["timestamps_included"] is False
        assert len(result.segments) == 1
