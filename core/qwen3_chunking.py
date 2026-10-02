"""
Qwen3-ASR の長音声チャンク処理(Qwen3ChunkingMixin)。

長音声の CHUNK_THRESHOLD_SEC 単位の分割、反復ループ検出時の再試行・
無音区間分割・反復部分除去のフォールバックを持つ。Qwen3ASREngine が継承し、
`_model` / `config` / `logger` / `_detect_repetition` / `_align_chunk` /
`_format_text_with_breaks` / `_language_name_to_code` / `CHUNK_THRESHOLD_SEC`
をエンジン側から利用する。
"""

import time
from typing import Any, Callable, List, Optional, Tuple, TYPE_CHECKING

from core.nemotron_engine import find_silence_boundary
from core.progress import emit_progress

if TYPE_CHECKING:
    import numpy as np

__all__ = ["Qwen3ChunkingMixin"]


class Qwen3ChunkingMixin:
    """Qwen3ASREngine の長音声チャンク処理を担うミックスイン。"""

    def _transcribe_long_audio(
        self,
        audio_path: str,
        duration: float,
        language: Optional[str],
        context: str = "",
        progress_callback: Optional[Callable] = None,
    ):
        """長音声を CHUNK_THRESHOLD_SEC 毎に分割して文字起こし、結果を結合する。

        Qwen3-ASR の内部チャンク処理でも長音声に対応しているが、
        RTX 4080 SUPER + torch 2.11.0+cu130 環境で15分超の音声で
        CUBLAS_STATUS_INTERNAL_ERROR が発生するため、外部で分割する。
        分割は音声ファイルを物理的に切り出すのではなく、(np.ndarray, sr)
        タプルを渡してメモリ上で処理する。

        各チャンクの生テキストを結合してから最後に1回だけ文節改行を適用する。
        (チャンク毎にフォーマットすると境界の文節が分断されるため)

        戻り値: (結合テキスト, 検出言語コード, 失敗チャンク数, 反復検出チャンク数,
        アライメントアイテムのリスト[config.include_timestamps=False時は空リスト])
        チャンクが失敗した場合は結果テキストに [チャンクN失敗] プレースホルダを
        挿入し、ユーザーが欠落に気づけるようにする。

        反復ループの是正(tc-ops #547是正、2026-09-27、真因未確定のまま無条件採用の
        采決定による)は`_transcribe_chunk_with_fallback()`に委譲する。1回目・再試行
        とも反復する場合、旧実装ではチャンク全体を[チャンクN反復検出のため破棄]に
        置換していたが、これは反復開始位置より前の正常な発話まで失う欠点があった。
        新実装は(c)反復開始位置以前の正常テキストを残して以降を切り詰める方式と、
        (d)チャンクを無音区間で2分割して再文字起こしするフォールバックを組み合わせ、
        正常チャンクの処理フロー・実行回数には影響を与えない。
        """
        import numpy as np
        from tqdm import tqdm

        # 音声を16kHzモノラルでロード
        import librosa
        audio, sr = librosa.load(str(audio_path), sr=16000, mono=True)

        chunk_samples = self.CHUNK_THRESHOLD_SEC * sr
        total_chunks = int(np.ceil(len(audio) / chunk_samples))

        raw_texts = []
        detected_lang = self.config.language
        failed_chunks = 0
        repeated_chunks = 0
        align_items_all: List[Any] = []

        emit_progress(progress_callback, f"文字起こし開始(全{total_chunks}チャンク)", 0.0)
        for i in tqdm(range(total_chunks), desc="音声文字起こし(分割)"):
            start_sample = i * chunk_samples
            end_sample = min(start_sample + chunk_samples, len(audio))
            chunk = audio[start_sample:end_sample]

            if len(chunk) < sr:  # 1秒未満の端数はスキップ
                continue

            chunk_start_time = time.time()
            # 幻覚リスク是正(bugfix 2026-08-05、tc-ops #439): contextを全チャンク一律で注入すると、
            # 無音・不明瞭なチャンク冒頭でヒント語彙が「発話された」と誤認される幻覚の原因になる
            # (config/context_hints.txt.sample参照)。最初のチャンクのみに限定して注入し、
            # 2チャンク目以降は空文字にすることで、当該チャンクでの幻覚混入を構造的に防止する
            # (副作用: 2チャンク目以降で固有名詞ヒントの効果は失われる。既知のトレードオフとして採用)。
            chunk_context = context if i == 0 else ""
            try:
                chunk_text, was_repeated, detected_lang_name = self._transcribe_chunk_with_fallback(
                    chunk, sr, chunk_context, language, chunk_label=str(i + 1), total_chunks=total_chunks,
                )
                if was_repeated:
                    repeated_chunks += 1

                if chunk_text:
                    raw_texts.append(chunk_text)
                    if self.config.include_timestamps and not chunk_text.startswith("\n[チャンク"):
                        offset_sec = start_sample / sr
                        align_items_all.extend(
                            self._align_chunk((chunk, sr), chunk_text, language, offset_sec)
                        )
                # 最初のチャンクの検出言語を使う
                if i == 0 and detected_lang_name:
                    detected_lang = self._language_name_to_code(detected_lang_name)

                chunk_elapsed = time.time() - chunk_start_time
                self.logger.info(
                    f"Chunk {i+1}/{total_chunks} done in {chunk_elapsed:.1f}s "
                    f"(lang={detected_lang})"
                )
                emit_progress(progress_callback, f"文字起こし中 {i + 1}/{total_chunks} チャンク完了", (i + 1) / total_chunks)
            except Exception as e:
                failed_chunks += 1
                self.logger.warning(f"Chunk {i+1}/{total_chunks} failed: {e}, inserting placeholder")
                # プレースホルダは前後で改行を強制(自然文ではないため)
                raw_texts.append(f"\n[チャンク{i+1}失敗]\n")
                emit_progress(progress_callback, f"文字起こし中 {i + 1}/{total_chunks} チャンク完了(失敗あり)", (i + 1) / total_chunks)
                continue

        # 生テキストを全チャンク結合してから、最後に1回だけ文節改行を適用
        # (チャンク毎にフォーマットすると境界の文節が分断されるため)
        #
        # bugfix(2026-08-03): チャンク境界がちょうど単語直後(句読点・空白を
        # 伴わない位置)で切れた場合、""での無区切り結合だと前チャンク末尾の
        # 単語と次チャンク先頭の単語が結合してしまう(実機再現・原因確定済み:
        # 実例「Nicolai Tangen」+「a way for...」→「Tangena way for...」)。
        # 半角スペース区切りに変更して単語結合を防止する。日本語文節(句読点
        # 終わり)の場合はスペースが1つ挟まるだけで、_format_text_with_breaks
        # 側でstrip()されるため表示上の影響はない。プレースホルダ
        # ([チャンクN失敗]等)前後の改行とも共存可能(実害なし)。
        raw_text = " ".join(raw_texts)
        text = self._format_text_with_breaks(raw_text)

        if failed_chunks > 0:
            self.logger.warning(
                f"Long audio transcription completed with {failed_chunks}/{total_chunks} failed chunks"
            )
        if repeated_chunks > 0:
            self.logger.warning(
                f"Long audio transcription completed with {repeated_chunks}/{total_chunks} chunks "
                f"triggering repetition-loop detection"
            )
        return text, detected_lang, failed_chunks, repeated_chunks, align_items_all

    # 無音分割フォールバック(d)を試みる最小チャンク長。これ未満では
    # find_silence_boundary()の探索窓(片側SILENCE_SEARCH_RADIUS_SEC秒)を
    # 確保できず、分割してもどちらかの半分がほぼ空になり得るため、
    # 分割を試みずに(c)の切り詰め/全体破棄に直接進む。
    _MIN_SPLIT_DURATION_SEC = 40.0

    def _split_audio_at_silence(self, chunk_audio: "np.ndarray", sr: int) -> Tuple["np.ndarray", "np.ndarray"]:
        """チャンク音声(np.ndarray)を、中間点付近の最も静かな位置で前半/後半に2分割する。

        tc-ops #546で実装した`core.nemotron_engine.find_silence_boundary()`
        (無音区間へ分割点を寄せる純粋関数)をそのまま転用する。両半分が空に
        ならないよう分割サンプル位置は[1, len-1]にクランプする。
        """
        total_duration_sec = len(chunk_audio) / sr
        split_sec = find_silence_boundary(chunk_audio, sr, total_duration_sec / 2, total_duration_sec)
        split_sample = int(split_sec * sr)
        split_sample = max(1, min(split_sample, len(chunk_audio) - 1))
        return chunk_audio[:split_sample], chunk_audio[split_sample:]

    def _transcribe_chunk_with_fallback(
        self,
        chunk_audio: "np.ndarray",
        sr: int,
        context: str,
        language: Optional[str],
        chunk_label: str,
        total_chunks: int,
        allow_split: bool = True,
    ) -> Tuple[str, bool, Optional[str]]:
        """チャンク単体を文字起こしし、反復ループ検出時の是正(tc-ops #547是正、
        2026-09-27、真因未確定のまま無条件採用の采決定による)を適用する。

        1回目が反復していれば同一チャンクを1回だけ再試行する(既存の安全網、
        bugfix 2026-08-03を踏襲)。再試行後も反復する場合、以下を順に試みる:

        (d) 無音区間2分割フォールバック(新規、采指示): `allow_split=True`かつ
            チャンク長が`_MIN_SPLIT_DURATION_SEC`以上の場合、チャンクを無音区間で
            前半/後半に2分割し、それぞれを独立に(`allow_split=False`で再帰的に)
            本メソッドへかける。正常チャンクの処理フローには影響しない
            (反復検出チャンクに限定した処理のため)。
        (c) 反復部分のみ除去(新規、采指示): (d)を適用できない場合(分割不可、
            または`allow_split=False`の再帰呼び出し自体が反復)、反復が開始する
            文字位置を`_detect_repetition()`で特定し、それ以前の正常テキストを
            残して以降を切り詰める。開始位置が先頭(0)で残せるテキストが無い場合は、
            旧実装と同じくチャンク全体を[チャンクN反復検出のため破棄]に置換する
            (フォールバックの最終段。既存の全体破棄方式を維持)。

        戻り値: (採用テキスト, 反復検出の有無, 検出言語名[Qwen3-ASRの生の言語名、
        検出失敗時はNone])
        """
        results = self._model.transcribe(
            audio=(chunk_audio, sr), context=context, language=language, return_time_stamps=False,
        )
        if not results:
            return "", False, None
        r = results[0]
        text = r.text.strip()
        is_repeated, _ = self._detect_repetition(text) if text else (False, None)
        if not is_repeated:
            return text, False, r.language

        self.logger.warning(
            f"Chunk {chunk_label}/{total_chunks}: repetition loop detected "
            f"({len(text)} chars), retrying once"
        )
        retry_results = self._model.transcribe(
            audio=(chunk_audio, sr), context=context, language=language, return_time_stamps=False,
        )
        retry_text = retry_results[0].text.strip() if retry_results else ""
        retry_is_repeated, retry_pos = (
            self._detect_repetition(retry_text) if retry_text else (False, None)
        )
        if retry_text and not retry_is_repeated:
            self.logger.info(f"Chunk {chunk_label}/{total_chunks}: retry succeeded")
            return retry_text, True, retry_results[0].language

        # (d) 無音区間2分割フォールバック
        min_split_samples = int(self._MIN_SPLIT_DURATION_SEC * sr)
        if allow_split and len(chunk_audio) >= min_split_samples:
            self.logger.warning(
                f"Chunk {chunk_label}/{total_chunks}: retry still repetitive, "
                f"attempting silence-split fallback"
            )
            left_audio, right_audio = self._split_audio_at_silence(chunk_audio, sr)
            left_text, _, left_lang = self._transcribe_chunk_with_fallback(
                left_audio, sr, context, language, f"{chunk_label}前半", total_chunks, allow_split=False,
            )
            right_text, _, right_lang = self._transcribe_chunk_with_fallback(
                right_audio, sr, "", language, f"{chunk_label}後半", total_chunks, allow_split=False,
            )
            combined = " ".join(t for t in (left_text, right_text) if t)
            return combined, True, (left_lang or right_lang)

        # (c) 反復部分のみ除去(分割不可、または分割後の半分自体が反復した場合の最終段)
        source_text = retry_text or text
        is_rep, pos = self._detect_repetition(source_text)
        if is_rep and pos:
            salvaged = source_text[:pos].strip()
            self.logger.warning(
                f"Chunk {chunk_label}/{total_chunks}: retry still repetitive, "
                f"truncating at repetition start (kept {len(salvaged)} chars)"
            )
            return salvaged, True, (retry_results[0].language if retry_text else r.language)

        self.logger.warning(
            f"Chunk {chunk_label}/{total_chunks}: retry still repetitive, "
            f"no salvageable prefix, discarding chunk"
        )
        return f"\n[チャンク{chunk_label}反復検出のため破棄]\n", True, None
