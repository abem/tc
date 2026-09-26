"""
Tests for core.transcription_interface.Qwen3ASREngine の反復ループ対策
(bugfix 2026-08-03)。

対象: output/20260803_082732_transcription.txt で実際に観測された、
ASRが同一文/単語を70回以上異常反復しチャンク末尾まで意味的に破壊される
事象への是正(反復検出・チャンク再試行・generation_config配線)。

フィクスチャ tests/fixtures/asr_repetition_incident_20260803.txt は、
実障害発生時にモデルが実際に生成した出力テキスト(該当箇所の生テキスト、
改行は_format_text_with_breaksによる後処理前の連続文字列に復元済み)を
そのまま使用する(証拠ベース: 合成データではなく実障害データで検証する)。
"""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "asr_repetition_incident_20260803.txt"


def _make_engine():
    from core.config import TranscriptionConfig
    from core.transcription_interface import Qwen3ASREngine

    config = TranscriptionConfig(model="Qwen/Qwen3-ASR-1.7B", language="ja", device="cpu")
    return Qwen3ASREngine(config)


class TestDetectRepetition:
    """(a) 反復検出関数が実障害テキストを実際に検知することの検証。

    tc-ops #547是正(2026-09-27、(c)反復部分のみ除去)により、戻り値が
    `bool`から`(bool, 反復開始位置の文字インデックスまたはNone)`へ拡張された。
    """

    def test_detects_real_incident_text(self):
        from core.transcription_interface import Qwen3ASREngine

        incident_text = FIXTURE_PATH.read_text(encoding="utf-8")
        is_repeated, position = Qwen3ASREngine._detect_repetition(incident_text)
        assert is_repeated is True
        assert position is not None
        # 反復開始位置以前が「正常な発話」であることの検証((c)の前提)。
        normal_prefix_len = incident_text.index("アジェンツ、")
        assert 0 < position <= normal_prefix_len

    def test_detects_incident_tail_only(self):
        """反復サイクルが始まった以降の断片だけでも検知できることを確認。"""
        from core.transcription_interface import Qwen3ASREngine

        incident_text = FIXTURE_PATH.read_text(encoding="utf-8")
        tail = incident_text[incident_text.index("アジェンツ、"):]
        is_repeated, position = Qwen3ASREngine._detect_repetition(tail)
        assert is_repeated is True
        assert position is not None

    def test_normal_text_not_flagged(self):
        """通常の(反復のない)文章は誤検知しないことを確認。"""
        from core.transcription_interface import Qwen3ASREngine

        incident_text = FIXTURE_PATH.read_text(encoding="utf-8")
        normal_prefix = incident_text[: incident_text.index("アジェンツ、")]
        assert Qwen3ASREngine._detect_repetition(normal_prefix) == (False, None)

    def test_short_phrase_repetition_detected(self):
        """短い相槌等の1〜2回程度の自然な繰り返しは誤検知しない一方、
        同一短文が閾値回数以上連続する異常系は検知することを確認。"""
        from core.transcription_interface import Qwen3ASREngine

        natural = "はい、はい、そうですね。分かりました。"
        assert Qwen3ASREngine._detect_repetition(natural) == (False, None)

        looped = "とても良いです。" * 5
        is_repeated, position = Qwen3ASREngine._detect_repetition(looped)
        assert is_repeated is True
        assert position == 0  # 冒頭から反復のみで構成されるテキストのため

    def test_empty_text_not_flagged(self):
        from core.transcription_interface import Qwen3ASREngine

        assert Qwen3ASREngine._detect_repetition("") == (False, None)


class TestChunkRetryFallback:
    """(b) チャンクループの再試行/フォールバック制御が動作することの検証。"""

    def _run_with_transcribe_side_effect(self, side_effect):
        engine = _make_engine()
        engine._model = MagicMock()
        engine._model.transcribe.side_effect = side_effect

        # 300s(=CHUNK_THRESHOLD_SEC) ちょうど1チャンク分の音声を模擬。
        sr = 16000
        fake_audio = np.zeros(engine.CHUNK_THRESHOLD_SEC * sr, dtype=np.float32)

        with patch("librosa.load", return_value=(fake_audio, sr)):
            text, lang, failed_chunks, repeated_chunks, align_items = engine._transcribe_long_audio(
                "dummy.wav", duration=engine.CHUNK_THRESHOLD_SEC, language="Japanese", context=""
            )
        return engine, text, lang, failed_chunks, repeated_chunks

    def test_retry_recovers_from_repetition(self):
        """1回目が反復、再試行で正常化するケース: 再試行結果が採用される。"""
        incident_text = FIXTURE_PATH.read_text(encoding="utf-8")
        clean_text = "これはテストの正常な文章です。"

        first = SimpleNamespace(text=incident_text, language="Japanese")
        retry = SimpleNamespace(text=clean_text, language="Japanese")

        engine, text, lang, failed_chunks, repeated_chunks = self._run_with_transcribe_side_effect(
            [[first], [retry]]
        )

        assert engine._model.transcribe.call_count == 2
        assert repeated_chunks == 1
        assert failed_chunks == 0
        assert clean_text in text
        # 反復テキストの一部(検知対象になった箇所)は破棄され残らないこと
        assert "アジェンツ" not in text

    def test_retry_still_repetitive_falls_back_to_silence_split(self):
        """1回目・再試行とも反復するが、無音分割(d、tc-ops #547是正・采指示)後の
        前半/後半はそれぞれ正常に書き起こせるケース: チャンク全体を破棄せず、
        分割後の内容を保持できることを確認。"""
        incident_text = FIXTURE_PATH.read_text(encoding="utf-8")
        left_clean = "前半の正常な発話です。"
        right_clean = "後半の正常な発話です。"

        first = SimpleNamespace(text=incident_text, language="Japanese")
        retry = SimpleNamespace(text=incident_text, language="Japanese")
        left = SimpleNamespace(text=left_clean, language="Japanese")
        right = SimpleNamespace(text=right_clean, language="Japanese")

        engine, text, lang, failed_chunks, repeated_chunks = self._run_with_transcribe_side_effect(
            [[first], [retry], [left], [right]]
        )

        assert engine._model.transcribe.call_count == 4
        assert repeated_chunks == 1
        assert left_clean in text
        assert right_clean in text
        assert "アジェンツ" not in text
        assert "[チャンク1反復検出のため破棄]" not in text

    def test_retry_and_both_split_halves_still_repetitive_inserts_placeholders(self):
        """1回目・再試行、および無音分割(d)後の前半/後半すべてが反復から
        回復できない最悪ケース: 旧実装のようにチャンク全体を無条件で破棄する
        のではなく、回復できなかった半分ごとにプレースホルダが挿入されること
        (反復テキストがそのまま結果に残らないという既存不変条件は維持)。"""
        looped = "とても良いです。" * 5
        side_effect = [[SimpleNamespace(text=looped, language="Japanese")]] * 6

        engine, text, lang, failed_chunks, repeated_chunks = self._run_with_transcribe_side_effect(
            side_effect
        )

        assert engine._model.transcribe.call_count == 6
        assert repeated_chunks == 1
        assert "反復検出のため破棄" in text
        assert "とても良いです" not in text

    def test_no_repetition_no_retry(self):
        """反復が無い正常系では再試行が起きず、transcribe()が1回だけ呼ばれること。"""
        clean_text = "これはテストの正常な文章です。"
        first = SimpleNamespace(text=clean_text, language="Japanese")

        engine, text, lang, failed_chunks, repeated_chunks = self._run_with_transcribe_side_effect(
            [[first]]
        )

        assert engine._model.transcribe.call_count == 1
        assert repeated_chunks == 0
        assert clean_text in text


class TestPartialRepetitionRemovalAndSplitFallback:
    """tc-ops #547是正(2026-09-27、真因未確定のまま采指示で無条件採用)の
    `_transcribe_chunk_with_fallback()`単体テスト。

    `_transcribe_long_audio()`を介さず`_transcribe_chunk_with_fallback()`を
    直接呼び出すことで、(c)反復部分のみ除去・(d)無音区間2分割フォールバックの
    分岐条件(チャンク長・`allow_split`)を`librosa.load`のモック無しで
    厳密に制御する。
    """

    def _make_engine_with_side_effect(self, side_effect):
        engine = _make_engine()
        engine._model = MagicMock()
        engine._model.transcribe.side_effect = side_effect
        return engine

    def test_truncation_keeps_prefix_when_chunk_too_short_to_split(self):
        """チャンク長が分割最小長(`_MIN_SPLIT_DURATION_SEC`)未満の場合、
        (d)分割は試みられず、(c)反復開始位置以前の正常テキストが保持されること。"""
        incident_text = FIXTURE_PATH.read_text(encoding="utf-8")
        engine = self._make_engine_with_side_effect([
            [SimpleNamespace(text=incident_text, language="Japanese")],
            [SimpleNamespace(text=incident_text, language="Japanese")],
        ])
        sr = 16000
        assert engine._MIN_SPLIT_DURATION_SEC > 10.0  # 前提: 10秒チャンクは分割最小長未満
        chunk_audio = np.zeros(int(sr * 10), dtype=np.float32)  # 10秒 < 分割最小長

        text, was_repeated, lang = engine._transcribe_chunk_with_fallback(
            chunk_audio, sr, context="", language="Japanese", chunk_label="1", total_chunks=1,
        )

        assert engine._model.transcribe.call_count == 2  # 分割呼び出しは発生しない
        assert was_repeated is True
        assert text.strip() != ""
        assert "アジェンツ" not in text
        assert "[チャンク1反復検出のため破棄]" not in text

    def test_truncation_discards_when_no_salvageable_prefix(self):
        """反復が冒頭(位置0)から始まり残せる正常テキストが無い場合、
        既存の全体破棄方式(プレースホルダ)を維持すること。"""
        looped = "とても良いです。" * 5
        engine = self._make_engine_with_side_effect([
            [SimpleNamespace(text=looped, language="Japanese")],
            [SimpleNamespace(text=looped, language="Japanese")],
        ])
        sr = 16000
        chunk_audio = np.zeros(int(sr * 10), dtype=np.float32)

        text, was_repeated, lang = engine._transcribe_chunk_with_fallback(
            chunk_audio, sr, context="", language="Japanese", chunk_label="1", total_chunks=1,
        )

        assert engine._model.transcribe.call_count == 2
        assert was_repeated is True
        assert text == "\n[チャンク1反復検出のため破棄]\n"

    def test_split_fallback_recurses_once_then_truncates_remaining_half(self):
        """分割(d)後の片側がなお反復するケース: 再帰は1段のみに限定され
        (allow_split=Falseで孫分割はしない)、その半分だけ(c)切り詰めが適用され、
        もう半分の正常な内容は保持されること(全体破棄にはならない)。"""
        incident_text = FIXTURE_PATH.read_text(encoding="utf-8")
        right_clean = "後半は正常です。"
        engine = self._make_engine_with_side_effect([
            [SimpleNamespace(text=incident_text, language="Japanese")],  # top first
            [SimpleNamespace(text=incident_text, language="Japanese")],  # top retry
            [SimpleNamespace(text=incident_text, language="Japanese")],  # left first (still repeats)
            [SimpleNamespace(text=incident_text, language="Japanese")],  # left retry (still repeats)
            [SimpleNamespace(text=right_clean, language="Japanese")],     # right first (clean)
        ])
        sr = 16000
        chunk_audio = np.zeros(int(sr * 300), dtype=np.float32)  # 300秒(分割対象)

        text, was_repeated, lang = engine._transcribe_chunk_with_fallback(
            chunk_audio, sr, context="", language="Japanese", chunk_label="1", total_chunks=1,
        )

        assert engine._model.transcribe.call_count == 5
        assert was_repeated is True
        assert right_clean in text
        assert "アジェンツ" not in text
        assert "[チャンク1反復検出のため破棄]" not in text

    def test_no_repetition_single_call_no_fallback(self):
        """反復が無い正常系では、フォールバック分岐に一切入らずtranscribe()が
        1回だけ呼ばれること(正常チャンクの処理フロー・実行回数への非影響確認)。"""
        clean_text = "これは正常な発話です。"
        engine = self._make_engine_with_side_effect([
            [SimpleNamespace(text=clean_text, language="Japanese")],
        ])
        sr = 16000
        chunk_audio = np.zeros(int(sr * 300), dtype=np.float32)

        text, was_repeated, lang = engine._transcribe_chunk_with_fallback(
            chunk_audio, sr, context="", language="Japanese", chunk_label="1", total_chunks=1,
        )

        assert engine._model.transcribe.call_count == 1
        assert was_repeated is False
        assert text == clean_text


class TestGenerationConfigWiring:
    """(c) generation_configへの反復抑制パラメータ配線が実際に
    generate()呼び出しへ渡っていることの検証。

    注記: transformersのgenerate()が明示指定しない生成パラメータを
    model.generation_configから継承する挙動自体はtransformersライブラリの
    既知仕様であり、本テストの対象外(ライブラリ側で担保される)。本テストは
    (1)_load_model()完了時点でgeneration_configに期待値が設定されていること、
    (2)qwen_asr内部の実際の生成呼び出し(_infer_asr_transformers相当の
    `model.generate(**inputs, max_new_tokens=...)`呼び出しパターン)の直前でも
    その設定が維持されたままgenerate()に渡る経路にあること、の2点を検証する。
    """

    def test_load_model_sets_generation_config(self):
        from core.transcription_interface import Qwen3ASREngine

        engine = _make_engine()

        fake_hf_model = MagicMock()
        fake_hf_model.generation_config = SimpleNamespace(
            repetition_penalty=1.0, no_repeat_ngram_size=0
        )
        fake_qwen_model = MagicMock()
        fake_qwen_model.model = fake_hf_model

        with patch("qwen_asr.Qwen3ASRModel.from_pretrained", return_value=fake_qwen_model):
            engine._load_model()

        assert engine._model.model.generation_config.repetition_penalty == Qwen3ASREngine.REPETITION_PENALTY
        assert engine._model.model.generation_config.no_repeat_ngram_size == Qwen3ASREngine.NO_REPEAT_NGRAM_SIZE

    def test_generation_config_reaches_generate_call(self):
        """qwen_asr内部の実際の generate() 呼び出しパターンを模擬し、
        呼び出し時点で generation_config に反復抑制値が渡った状態にあることを確認。
        """
        from core.transcription_interface import Qwen3ASREngine

        engine = _make_engine()

        fake_hf_model = MagicMock()
        fake_hf_model.generation_config = SimpleNamespace(
            repetition_penalty=1.0, no_repeat_ngram_size=0
        )
        fake_qwen_model = MagicMock()
        fake_qwen_model.model = fake_hf_model
        fake_qwen_model.max_new_tokens = 1024

        with patch("qwen_asr.Qwen3ASRModel.from_pretrained", return_value=fake_qwen_model):
            engine._load_model()

        # qwen_asr/inference/qwen3_asr.py:510 の実際の呼び出しパターンを再現:
        #   self.model.generate(**inputs, max_new_tokens=self.max_new_tokens)
        observed_generation_config_at_call = {}

        def fake_generate(**kwargs):
            observed_generation_config_at_call["repetition_penalty"] = (
                fake_hf_model.generation_config.repetition_penalty
            )
            observed_generation_config_at_call["no_repeat_ngram_size"] = (
                fake_hf_model.generation_config.no_repeat_ngram_size
            )
            observed_generation_config_at_call["kwargs"] = kwargs
            return MagicMock()

        fake_hf_model.generate = fake_generate
        fake_hf_model.generate(input_ids=MagicMock(), max_new_tokens=fake_qwen_model.max_new_tokens)

        assert observed_generation_config_at_call["repetition_penalty"] == Qwen3ASREngine.REPETITION_PENALTY
        assert observed_generation_config_at_call["no_repeat_ngram_size"] == Qwen3ASREngine.NO_REPEAT_NGRAM_SIZE
        # repetition_penalty/no_repeat_ngram_size は明示kwargsとして渡していない
        # (generation_config側からの継承経路であることの確認)
        assert "repetition_penalty" not in observed_generation_config_at_call["kwargs"]
        assert "no_repeat_ngram_size" not in observed_generation_config_at_call["kwargs"]


class TestChunkJoinWhitespace:
    """チャンク境界の無区切り結合バグ(bugfix 2026-08-03)への回帰テスト。

    実障害: 実際の該当音声(chunk index 6/7、境界1800s/2100s/2400s)を
    _transcribe_long_audio()と同一の切り方で個別に実機ASR実行したところ、
    chunk6が"...Nicolai Tangen"で終わり、chunk7が"a way for the government..."
    から始まっており、""での無区切り結合により観測どおりの
    "Nicolai Tangena way for the government..."という誤変換が実機で再現した
    (原因確定済み)。本テストはその実測データをフィクスチャ化して検証する。
    """

    def _run_two_chunks(self, chunk_texts):
        engine = _make_engine()
        engine._model = MagicMock()
        engine._model.transcribe.side_effect = [
            [SimpleNamespace(text=t, language="English")] for t in chunk_texts
        ]

        sr = 16000
        # 2チャンク分(600s)の音声を模擬。
        fake_audio = np.zeros(2 * engine.CHUNK_THRESHOLD_SEC * sr, dtype=np.float32)

        with patch("librosa.load", return_value=(fake_audio, sr)):
            text, lang, failed_chunks, repeated_chunks, align_items = engine._transcribe_long_audio(
                "dummy.wav", duration=2 * engine.CHUNK_THRESHOLD_SEC, language="English", context=""
            )
        return text

    def test_word_at_chunk_boundary_not_glued(self):
        """実測データ(chunk6末尾/chunk7先頭)そのままで単語結合が解消されること。"""
        chunk6_tail = (
            "You know one of the speakers in this class is Nicolai Tangen"
        )
        chunk7_head = (
            "a way for the government to redistribute income from taxpayers."
        )
        text = self._run_two_chunks([chunk6_tail, chunk7_head])

        assert "Tangena way" not in text
        assert "Nicolai Tangen a way for the government" in text

    def test_failed_chunk_placeholder_still_renders(self):
        """境界結合の是正(space join化)後も、失敗チャンクのプレースホルダ表示に
        回帰が無いこと(条件2: 既存の反復検出・プレースホルダ処理との非干渉確認)。"""
        engine = _make_engine()
        engine._model = MagicMock()
        engine._model.transcribe.side_effect = [
            [SimpleNamespace(text="最初のチャンクです。", language="Japanese")],
            RuntimeError("simulated chunk failure"),
        ]

        sr = 16000
        fake_audio = np.zeros(2 * engine.CHUNK_THRESHOLD_SEC * sr, dtype=np.float32)

        with patch("librosa.load", return_value=(fake_audio, sr)):
            text, lang, failed_chunks, repeated_chunks, align_items = engine._transcribe_long_audio(
                "dummy.wav", duration=2 * engine.CHUNK_THRESHOLD_SEC, language="Japanese", context=""
            )

        assert failed_chunks == 1
        assert "[チャンク2失敗]" in text
        assert "最初のチャンクです。" in text
