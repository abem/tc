"""
Qwen3-ASR ベースの文字起こしエンジン。

長音声のチャンク処理は core.qwen3_chunking(Qwen3ChunkingMixin)、
テキスト整形・反復検出は core.qwen3_text に分離している。
"""

import os
import sys
import threading
import traceback
from pathlib import Path
from types import SimpleNamespace
from typing import Any, List, Optional, Tuple

from core.config import TranscriptionConfig
from core.qwen3_chunking import Qwen3ChunkingMixin
from core.qwen3_text import (
    core_char_count,
    detect_repetition,
    format_text_with_breaks,
    language_name_to_code,
    match_fragments_to_alignment,
)
from core.transcription_types import (
    TranscriptionEngine,
    TranscriptionResult,
    TranscriptionSegment,
)
from core.utils import get_audio_duration

__all__ = ["Qwen3ASREngine"]


class Qwen3ASREngine(Qwen3ChunkingMixin, TranscriptionEngine):
    """Qwen3-ASR based transcription engine.

    Qwen3-ASR (qwen-asr package) はロングオーディオ対応・タイムスタンプ内蔵で、
    Whisper のようにチャンク分割が不要。2026年ベンチマークで最上位の精度。
    """

    def __init__(self, config: TranscriptionConfig):
        super().__init__(config)
        self._model = None
        self._aligner = None
        self._aligner_unavailable = False

    def get_engine_name(self) -> str:
        return f"qwen3-asr-{self.config.model}"

    @staticmethod
    def is_qwen3_model(model_name: str) -> bool:
        """モデル名が Qwen3-ASR 系かどうかを判定。"""
        name = (model_name or "").lower()
        return "qwen3-asr" in name or "qwen3_asr" in name

    def _load_model(self):
        """Qwen3ASRModel を遅延ロード。

        注意: UnifiedModelManager(共有キャッシュ/メモリ管理)を経由せず、
        Qwen3ASRModel.from_pretrained を直接呼ぶ。qwen_asr の API が独自の
        モデル管理を行うため model_manager に適合しない。長時間稼働プロセスで
        複数プロファイルを切替える場合は、Qwen3 モデルのメモリが
        memory_limit 予算に計上されないことに留意。
        """
        if self._model is None:
            # 診断ログ(tc-ops #441調査専用、調査完了後に削除またはコミット要否を計と協議する)
            self.logger.info(
                "qwen_asr import直前診断 pid=%s thread=%s cwd=%s sys.path=%s",
                os.getpid(), threading.current_thread().name, os.getcwd(), sys.path,
            )
            try:
                from qwen_asr import Qwen3ASRModel
            except BaseException:
                self.logger.error(
                    "qwen_asr import失敗診断 pid=%s thread=%s traceback=%s",
                    os.getpid(), threading.current_thread().name, traceback.format_exc(),
                )
                raise
            self.logger.info(
                "qwen_asr import成功診断 pid=%s thread=%s", os.getpid(), threading.current_thread().name
            )
            import torch

            device = self.config.device
            # device_map は "cuda:0" / "cpu" の形式が必要
            device_map = f"{device}:0" if device.startswith("cuda") else device

            self._model = Qwen3ASRModel.from_pretrained(
                self.config.model,
                dtype=torch.bfloat16 if device.startswith("cuda") else torch.float32,
                device_map=device_map,
                max_new_tokens=1024,  # 長音声向けに十分確保
            )

            # 反復ループ対策(bugfix 2026-08-03): 同一文/単語が数十回異常反復し
            # チャンクが意味的に破壊される事象への予防策。qwen_asr の公開API
            # (from_pretrained/transcribe)には反復抑制パラメータの設定経路が
            # 無いため、ロード済みHFモデル(Qwen3ASRModel.model、公開属性)の
            # generation_config を直接設定する。transformers の generate() は
            # 明示指定しない生成パラメータを generation_config から補うため、
            # ここで一度設定すれば以降の全 generate() 呼び出しに反映される。
            self._model.model.generation_config.repetition_penalty = self.REPETITION_PENALTY
            self._model.model.generation_config.no_repeat_ngram_size = self.NO_REPEAT_NGRAM_SIZE

    # 反復抑制パラメータの既定値。repetition_penalty > 1.0 で同一トークン列の
    # 再選択確率を下げ、no_repeat_ngram_size > 0 で同一N-gramの再生成を禁止する。
    # 値は一般的な過剰抑制回避レンジ(HF標準の目安)を採用(実測チューニングは
    # 別途フォローアップ課題)。
    REPETITION_PENALTY = 1.3
    NO_REPEAT_NGRAM_SIZE = 4

    # タイムスタンプ付与(config.include_timestamps=True時のみ使用)。
    # qwen_asr同梱のQwen3ForcedAligner(コードは同梱済みだがモデル重みは別
    # チェックポイントで初回利用時に追加ダウンロードが必要)を、メインASR
    # モデルとは独立に単独ロード・呼び出しする(2段構成: ASR実行→音声+ASR
    # テキストをアライナーに渡してforced alignmentで単語/文字単位の時刻を得る)。
    # 実測(RTX 4080 SUPER): ASRモデル(bf16)ロード後 約11.3GB、アライナー追加
    # ロード後 約12.5GB/16.4GB(追加約1.2GB)。
    FORCED_ALIGNER_MODEL = "Qwen/Qwen3-ForcedAligner-0.6B"

    def _load_aligner(self) -> bool:
        """ForcedAligner を遅延ロードする。成功した場合True、失敗した場合False
        を返し以後は再試行しない(config.include_timestamps=True時のみ呼ばれる、
        失敗時はタイムスタンプなしの通常出力にフォールバックする設計)。
        """
        if self._aligner is not None:
            return True
        if self._aligner_unavailable:
            return False

        try:
            from qwen_asr.inference.qwen3_forced_aligner import Qwen3ForcedAligner
            import torch

            device = self.config.device
            device_map = f"{device}:0" if device.startswith("cuda") else device

            self._aligner = Qwen3ForcedAligner.from_pretrained(
                self.FORCED_ALIGNER_MODEL,
                dtype=torch.bfloat16 if device.startswith("cuda") else torch.float32,
                device_map=device_map,
            )
            return True
        except Exception as e:
            self.logger.warning(
                f"ForcedAlignerのロードに失敗しました。タイムスタンプなしで続行します: {e}"
            )
            self._aligner_unavailable = True
            return False

    def _align_chunk(self, audio, text: str, language: Optional[str], offset_sec: float):
        """1チャンク(または短音声全体)の音声+ASRテキストをForcedAlignerに渡し、
        時刻オフセット(チャンク開始秒)を加算したアイテムリストを返す。
        audioはファイルパス(str)または(np.ndarray, sr)タプルのいずれか
        (Qwen3ForcedAligner.align()と同じ入力形式)。失敗時は空リスト
        (呼び出し側はタイムスタンプなしとして扱う)。
        """
        if not text.strip():
            return []
        if not self._load_aligner():
            return []
        try:
            results = self._aligner.align(audio=audio, text=text, language=language)
            if not results:
                return []
            items = []
            for it in results[0].items:
                items.append(SimpleNamespace(
                    text=it.text,
                    start_time=it.start_time + offset_sec,
                    end_time=it.end_time + offset_sec,
                ))
            return items
        except Exception as e:
            self.logger.warning(f"ForcedAlignerの実行に失敗しました(このチャンクはタイムスタンプなし): {e}")
            return []

    # 長音声を分割する閾値(秒)。
    # 実測で10分(600s)までは成功、15分(900s)で CUBLAS_STATUS_INTERNAL_ERROR が
    # 発生することを確認(RTX 4080 SUPER / torch 2.11.0+cu130 / bfloat16)。
    # Windows 側を含むシステム全体の GPU 負荷ピークを抑えるため、
    # 安全側に振って 5 分(300s)をチャンク上限とする(実測で成功済み)。
    CHUNK_THRESHOLD_SEC = 300

    def transcribe(self, audio_path: str, **kwargs) -> TranscriptionResult:
        """Qwen3-ASR で文字起こし。長音声は自動的に分割して処理。"""
        self.validate_audio_file(audio_path)

        self.perf_logger.start_timing(f"transcribe_{Path(audio_path).name}")

        try:
            self._load_model()

            # 言語マップ (TranscriptionConfig.language -> Qwen3 の言語名)
            lang_map = {"ja": "Japanese", "en": "English"}
            language = lang_map.get(self.config.language, None)

            duration = self._get_audio_duration(audio_path)
            failed_chunks = 0
            repeated_chunks = 0
            align_items: List[Any] = []
            if duration > self.CHUNK_THRESHOLD_SEC:
                # 長音声: 分割して処理
                self.logger.info(
                    f"Audio is {duration:.0f}s (>{self.CHUNK_THRESHOLD_SEC}s), "
                    f"splitting into chunks for stable processing"
                )
                text, detected_language, failed_chunks, repeated_chunks, align_items = self._transcribe_long_audio(
                    audio_path, duration, language, self.config.context,
                    progress_callback=kwargs.get("progress_callback"),
                )
            else:
                # 短音声: そのまま処理
                results = self._model.transcribe(
                    audio=str(audio_path),
                    context=self.config.context,
                    language=language,
                    return_time_stamps=False,
                )
                if not results:
                    raise RuntimeError("Qwen3-ASR returned no results")
                r = results[0]
                detected_language = self._language_name_to_code(
                    r.language or self.config.language
                )
                raw_text = r.text.strip()
                # 文節改行フォーマットを適用
                text = self._format_text_with_breaks(raw_text)

                if self.config.include_timestamps:
                    align_items = self._align_chunk(str(audio_path), raw_text, language, offset_sec=0.0)

            processing_time = self.perf_logger.end_timing(f"transcribe_{Path(audio_path).name}")

            # 結果を構築: タイムスタンプが取得できた場合は文節単位の複数セグメント、
            # そうでない場合(config.include_timestamps=False、またはアライナー
            # ロード/実行失敗によるフォールバック)は従来どおり全体を1セグメントとする。
            timestamps_included = False
            fragments = [line for line in text.split("\n") if line.strip()]
            if self.config.include_timestamps and align_items and fragments:
                boundaries = self._match_fragments_to_alignment(fragments, align_items)
                segments = [
                    TranscriptionSegment(start=start, end=end, text=frag, language=detected_language)
                    for frag, (start, end) in zip(fragments, boundaries)
                ]
                timestamps_included = True
            else:
                segments = [TranscriptionSegment(
                    start=0.0,
                    end=duration,
                    text=text,
                    language=detected_language,
                )]

            result = TranscriptionResult(
                text=text,
                segments=segments,
                language=detected_language,
                duration=duration,
                processing_time=processing_time,
                model_name=self.config.model,
                has_speakers=False,
                metadata={
                    "detected_language": detected_language,
                    "chunked": duration > self.CHUNK_THRESHOLD_SEC,
                    "failed_chunks": failed_chunks,
                    "repeated_chunks": repeated_chunks,
                    "timestamps_included": timestamps_included,
                },
            )

            self.logger.info(f"Transcription completed: {len(text)} characters")
            return result

        except Exception as e:
            self.logger.error(f"Transcription failed: {str(e)}")
            raise

    def _get_audio_duration(self, audio_path: str) -> float:
        """音声ファイルの長さを取得。"""
        return get_audio_duration(audio_path)

    @staticmethod
    def _core_char_count(text: str) -> int:
        return core_char_count(text)

    @staticmethod
    def _match_fragments_to_alignment(fragments, align_items):
        return match_fragments_to_alignment(fragments, align_items)

    @staticmethod
    def _detect_repetition(text: str, max_cycle: int = 40, min_repeats: int = 3) -> Tuple[bool, Optional[int]]:
        """反復ループ検出(実体は core.qwen3_text.detect_repetition)。"""
        return detect_repetition(text, max_cycle, min_repeats)

    @staticmethod
    def _format_text_with_breaks(text: str) -> str:
        """文節区切りで改行する(実体は core.qwen3_text.format_text_with_breaks)。"""
        return format_text_with_breaks(text)

    @staticmethod
    def _language_name_to_code(name: Optional[str]) -> str:
        """'Japanese' -> 'ja' のように言語名をコードに変換。"""
        return language_name_to_code(name)
