"""
Unified transcription interface.
Consolidates all transcribe() method implementations into a single, consistent API.

警告抑制は suppress_warnings.py に一元化(各エントリポイントで import 済)。
このモジュール内では個別の filterwarnings を持たない。
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Tuple, Callable, TYPE_CHECKING
from dataclasses import dataclass
from types import SimpleNamespace
import os
import sys
import threading
import time
import traceback
from pathlib import Path
import torch

if TYPE_CHECKING:
    import numpy as np

from core.config import TranscriptionConfig
from core.logging import UnifiedLogger, PerformanceLogger
from core.model_manager import get_global_model_manager
from core.progress import emit_progress
from core.utils import DEFAULT_AUDIO_DURATION_SEC, get_audio_duration


@dataclass
class TranscriptionSegment:
    """Represents a transcribed segment with metadata."""
    start: float
    end: float
    text: str
    speaker: Optional[str] = None
    confidence: Optional[float] = None
    language: Optional[str] = None


@dataclass
class TranscriptionResult:
    """Complete transcription result with metadata."""
    text: str
    segments: List[TranscriptionSegment]
    language: str
    duration: float
    processing_time: float
    model_name: str
    has_speakers: bool = False
    metadata: Optional[Dict[str, Any]] = None


class TranscriptionEngine(ABC):
    """Abstract base class for all transcription engines."""
    
    def __init__(self, config: TranscriptionConfig):
        self.config = config
        self.logger = UnifiedLogger.get_logger(self.__class__.__name__)
        self.perf_logger = PerformanceLogger(self.__class__.__name__)
        self.model_manager = get_global_model_manager()
    
    @abstractmethod
    def transcribe(self, audio_path: str, **kwargs) -> TranscriptionResult:
        """Transcribe audio file and return structured result."""
        pass
    
    @abstractmethod
    def get_engine_name(self) -> str:
        """Get the name of this transcription engine."""
        pass
    
    def validate_audio_file(self, audio_path: str) -> bool:
        """Validate that the audio file exists and is accessible."""
        path = Path(audio_path)
        if not path.exists():
            raise FileNotFoundError(f"Audio file not found: {audio_path}")
        if not path.is_file():
            raise ValueError(f"Path is not a file: {audio_path}")
        return True


class WhisperTranscriptionEngine(TranscriptionEngine):
    """Whisper-based transcription engine."""
    
    def __init__(self, config: TranscriptionConfig):
        super().__init__(config)
        self._model = None
        self._processor = None
    
    def get_engine_name(self) -> str:
        return f"whisper-{self.config.model}"
    
    def _load_model(self):
        """Load the Whisper model if not already loaded."""
        if self._model is None:
            model_components = self.model_manager.load_model(
                model_name=self.config.model,
                model_type="whisper",
                device=self.config.device
            )
            self._model = model_components["model"]
            self._processor = model_components["processor"]
    
    def transcribe(self, audio_path: str, **kwargs) -> TranscriptionResult:
        """Transcribe audio using Whisper model with full functionality."""
        self.validate_audio_file(audio_path)

        self.perf_logger.start_timing(f"transcribe_{Path(audio_path).name}")
        
        try:
            # Load model
            self._load_model()
            
            # Get full transcription with original functionality
            full_text = self._transcribe_with_original_logic(
                audio_path, progress_callback=kwargs.get("progress_callback")
            )
            
            processing_time = self.perf_logger.end_timing(f"transcribe_{Path(audio_path).name}")
            
            # Parse the timestamped text into segments
            segments = self._parse_timestamped_text(full_text)
            
            # Create structured result
            result = TranscriptionResult(
                text=full_text,
                segments=segments,
                language=self.config.language,
                duration=self._get_audio_duration(audio_path),
                processing_time=processing_time,
                model_name=self.config.model,
                has_speakers=False
            )
            
            self.logger.info(f"Transcription completed: {len(full_text)} characters")
            return result
            
        except Exception as e:
            self.logger.error(f"Transcription failed: {str(e)}")
            raise
    
    def _parse_timestamped_text(self, text: str) -> List[TranscriptionSegment]:
        """Parse timestamped text into segments."""
        import re
        segments = []
        
        # Pattern to match [MM:SS] timestamp format
        pattern = r'\[(\d{2}):(\d{2})\]\s*(.+?)(?=\[|\Z)'
        matches = re.findall(pattern, text, re.DOTALL)
        
        for match in matches:
            minutes, seconds, segment_text = match
            start_time = int(minutes) * 60 + int(seconds)
            
            segment = TranscriptionSegment(
                start=start_time,
                end=start_time + 30,  # Default 30-second segments
                text=segment_text.strip(),
                language=self.config.language
            )
            segments.append(segment)
        
        # If no timestamps found, create single segment
        if not segments and text.strip():
            segments = [TranscriptionSegment(
                start=0.0,
                end=self._get_audio_duration_fallback(),
                text=text.strip(),
                language=self.config.language
            )]
        
        return segments
    
    def _get_audio_duration_fallback(self) -> float:
        """Fallback audio duration."""
        return DEFAULT_AUDIO_DURATION_SEC

    def _get_audio_duration(self, audio_path: str) -> float:
        """Get audio file duration."""
        return get_audio_duration(audio_path)
    
    def _transcribe_with_original_logic(self, audio_path: str, progress_callback: Optional[Callable] = None) -> str:
        """Transcribe using the original WhisperTranscriber logic for quality."""
        from tqdm import tqdm
        
        # Audio preprocessing
        audio, sr = self._preprocess_audio(audio_path)
        
        # Create chunks (30-second intervals)
        chunk_size = 30 * sr
        chunks = self._create_chunks(audio, chunk_size)
        
        if not chunks:
            return ""
        
        texts = []

        # Process each chunk with timestamps
        for i, chunk in enumerate(tqdm(chunks, desc="音声文字起こし")):
            chunk_start_seconds = i * 30
            emit_progress(progress_callback, f"文字起こし中 {i + 1}/{len(chunks)}", i / len(chunks))

            # Process single chunk with proper attention mask
            inputs = self._processor(
                chunk,
                sampling_rate=sr,
                return_tensors="pt",
                padding=True,
                truncation=True
            ).to(self.config.device)

            # Ensure attention mask is set to avoid warnings
            if not hasattr(inputs, 'attention_mask') or inputs.attention_mask is None:
                inputs.attention_mask = torch.ones(inputs.input_features.shape[:2], dtype=torch.long, device=self.config.device)

            # Generate transcription with modern API
            # (警告抑制は suppress_warnings.py に一元化済みのため、ここでは持たない)
            with torch.no_grad():

                # Prepare generation kwargs with modern parameters
                generation_kwargs = {
                    "language": self.config.language,
                    "task": "transcribe",
                    "max_new_tokens": 400,
                    "do_sample": False,
                    "temperature": 0.0,
                    "use_cache": True,
                    "pad_token_id": self._processor.tokenizer.eos_token_id,
                    "suppress_tokens": None
                }

                # Create proper generate arguments with attention_mask
                generate_kwargs = generation_kwargs.copy()

                # Remove attention_mask from generation_kwargs and pass it separately
                if 'attention_mask' in generate_kwargs:
                    del generate_kwargs['attention_mask']

                # Generate with proper attention_mask handling
                if hasattr(inputs, 'attention_mask') and inputs.attention_mask is not None:
                    generated_ids = self._model.generate(
                        inputs.input_features,
                        attention_mask=inputs.attention_mask,
                        **generate_kwargs
                    )
                else:
                    generated_ids = self._model.generate(
                        inputs.input_features,
                        **generate_kwargs
                    )
            
            # Decode text
            text = self._processor.batch_decode(
                generated_ids, 
                skip_special_tokens=True
            )[0]
            
            # Add timestamp and format text
            if text.strip():
                timestamped_text = self._add_timestamps_to_text(text, chunk_start_seconds)
                if timestamped_text:
                    texts.append(timestamped_text)
        
        # Join and ensure timestamps are at line start
        final_output = "\n".join(texts)
        return self._ensure_timestamps_at_line_start(final_output)
    
    def _preprocess_audio(self, audio_path: str):
        """Preprocess audio (convert to mono, resample)."""
        import soundfile as sf
        import numpy as np
        
        audio, sr = sf.read(audio_path)
        
        # Convert to mono if stereo
        if len(audio.shape) > 1:
            audio = np.mean(audio, axis=1)
        
        # Resample to 16kHz if needed
        if sr != 16000:
            try:
                # Use librosa for stable resampling
                import librosa
                audio = librosa.resample(audio, orig_sr=sr, target_sr=16000)
            except (ImportError, Exception):
                # Fallback: scipy resampling
                try:
                    import scipy.signal
                    audio = scipy.signal.resample(audio, int(len(audio) * 16000 / sr))
                except Exception:
                    # Last resort: simple linear interpolation
                    import numpy as np
                    audio = np.interp(
                        np.linspace(0, len(audio), int(len(audio) * 16000 / sr)),
                        np.arange(len(audio)),
                        audio
                    )
            sr = 16000
        
        return audio, sr
    
    def _create_chunks(self, audio, chunk_size):
        """Create audio chunks for processing."""
        chunks = []
        for i in range(0, len(audio), chunk_size):
            chunk = audio[i:i + chunk_size]
            if len(chunk) > 0:
                chunks.append(chunk)
        return chunks
    
    def _add_timestamps_to_text(self, text: str, start_seconds: int) -> str:
        """Add timestamps to text segments."""
        if not text.strip():
            return ""
        
        # Format timestamp as [MM:SS]
        minutes = start_seconds // 60
        seconds = start_seconds % 60
        timestamp = f"[{minutes:02d}:{seconds:02d}]"
        
        # Clean and format text
        text = text.strip()
        return f"{timestamp} {text}"
    
    def _ensure_timestamps_at_line_start(self, text: str) -> str:
        """Ensure timestamps are at the beginning of lines."""
        import re
        
        # Split into lines and process each
        lines = text.split('\n')
        processed_lines = []
        
        for line in lines:
            line = line.strip()
            if line:
                # Ensure timestamp is at the start
                if not line.startswith('['):
                    # Look for timestamp pattern in the line
                    timestamp_match = re.search(r'\[(\d{2}):(\d{2})\]', line)
                    if timestamp_match:
                        timestamp = timestamp_match.group(0)
                        text_part = line.replace(timestamp, '').strip()
                        line = f"{timestamp} {text_part}"
                processed_lines.append(line)
        
        return '\n'.join(processed_lines)


class Qwen3ASREngine(TranscriptionEngine):
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

    @staticmethod
    def _core_char_count(text: str) -> int:
        """句読点等を除いた実質文字数。ForcedAlignerは句読点を除去した実質
        文字/単語単位でトークン化するため、フラグメントとアライナー出力の
        対応付け(_match_fragments_to_alignment)の消費量算出に使う。
        """
        import unicodedata

        count = 0
        for ch in text:
            if ch == "'":
                count += 1
                continue
            category = unicodedata.category(ch)
            if category.startswith("L") or category.startswith("N"):
                count += 1
        return count

    @staticmethod
    def _match_fragments_to_alignment(fragments, align_items):
        """文節フラグメント列(_format_text_with_breaksと同じ区切り)を
        ForcedAlignerの出力アイテム列に近似的に対応付け、各フラグメントの
        (start_time, end_time)のリストを返す。

        ForcedAlignerは句読点を除いた実質文字/単語単位でトークン化するため、
        各フラグメントの実質文字数ぶんアイテムを順に消費し、先頭アイテムの
        start_timeと消費末尾アイテムのend_timeを区間として採用する。厳密な
        1対1対応の保証はない近似処理(音声位置の目安として十分な精度)。
        """
        results = []
        idx = 0
        n = len(align_items)
        for frag in fragments:
            target = Qwen3ASREngine._core_char_count(frag)
            if target == 0 or idx >= n:
                prev_end = results[-1][1] if results else 0.0
                results.append((prev_end, prev_end))
                continue
            start_idx = idx
            consumed = 0
            while idx < n and consumed < target:
                consumed += len(align_items[idx].text)
                idx += 1
            end_idx = max(idx - 1, start_idx)
            results.append((align_items[start_idx].start_time, align_items[end_idx].end_time))
        return results

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
        from core.nemotron_engine import find_silence_boundary

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

    @staticmethod
    def _detect_repetition(text: str, max_cycle: int = 40, min_repeats: int = 3) -> Tuple[bool, Optional[int]]:
        """句読点区切りの文節列に、同一の文節シーケンス(長さ1〜max_cycle)が
        min_repeats回以上連続して繰り返される箇所がないかを検出する。

        ASRの反復ループ(実障害: 「アジェンツは、ツールコールの高品質と正確さを
        必要とするため...」という1文が単語単位の改行を伴い70回以上連続反復)を
        検知するための軽量ヒューリスティック。正規表現の後方参照
        (`(.+)\\1{2,}`)はバックトラック爆発のリスクがあるため使わず、
        文節リストに対する固定長スライド窓比較で実装する。

        戻り値: (反復を検出したか, 反復が開始する文字インデックス[検出時のみ、
        テキスト先頭からの文字オフセット。未検出時はNone])。反復開始位置は
        tc-ops #547是正(2026-09-27、(c)反復部分のみ除去)で追加した。呼び出し元は
        `text[:pos]`で反復開始前の正常テキストのみを残せる。
        """
        import re

        fragments = [s for s in re.split(r'(?<=[。、！？!?])', text) if s.strip()]
        n = len(fragments)
        if n < min_repeats:
            return False, None

        for cycle in range(1, max_cycle + 1):
            window_span = cycle * min_repeats
            if n < window_span:
                break
            for i in range(0, n - window_span + 1):
                unit = fragments[i:i + cycle]
                if all(
                    fragments[i + k * cycle:i + (k + 1) * cycle] == unit
                    for k in range(1, min_repeats)
                ):
                    position = sum(len(f) for f in fragments[:i])
                    return True, position
        return False, None

    @staticmethod
    def _format_text_with_breaks(text: str) -> str:
        """テキストを文節区切りで改行する。

        句点(。)・読点(、)・感嘆符(！/!)・疑問符(？/?) の後に改行を入れる。
        タイムスタンプは付与しない(実時間の精度に確証がないため誤解を避ける)。
        """
        import re

        # 文節区切り文字で分割(区切り文字も保持)
        sentences = re.split(r'(?<=[。、！？!?])', text)
        sentences = [s.strip() for s in sentences if s.strip()]

        if not sentences:
            return text.strip()

        return "\n".join(sentences)

    @staticmethod
    def _language_name_to_code(name: Optional[str]) -> str:
        """'Japanese' -> 'ja' のように言語名をコードに変換。"""
        mapping = {"japanese": "ja", "english": "en"}
        return mapping.get((name or "").lower(), name or "ja")

    def _get_audio_duration(self, audio_path: str) -> float:
        """音声ファイルの長さを取得。"""
        return get_audio_duration(audio_path)


class UnifiedTranscriber:
    """Unified transcription interface that handles all transcription types."""
    
    def __init__(self,
                 transcription_config: TranscriptionConfig):
        self.transcription_config = transcription_config

        self.logger = UnifiedLogger.get_logger(self.__class__.__name__)
        self.perf_logger = PerformanceLogger(self.__class__.__name__)

        # Initialize engines
        # モデル名でエンジンを切替(Nemotron系→専用サブプロセスエンジン、
        # Qwen3-ASR系→専用エンジン、それ以外はWhisper)。
        # nemotron判定はqwen3判定より前に置く(tc-ops #546 Phase2設計report§2)。
        # is_nemotron_model/is_qwen3_modelの判定文字列は互いに排他的なため、
        # この順序自体は既存モデル名の解決結果に影響しない。
        # core.nemotron_engineはローカルimportとする(循環import回避。
        # nemotron_engine.py側がTranscriptionEngine等を本モジュールからimportするため)。
        from core.nemotron_engine import is_nemotron_model, NemotronSubprocessEngine
        if is_nemotron_model(transcription_config.model):
            self.transcription_engine = NemotronSubprocessEngine(transcription_config)
        elif Qwen3ASREngine.is_qwen3_model(transcription_config.model):
            self.transcription_engine = Qwen3ASREngine(transcription_config)
        else:
            self.transcription_engine = WhisperTranscriptionEngine(transcription_config)

    def transcribe(self,
                   audio_path: str,
                   progress_callback: Optional[Callable] = None,
                   **kwargs) -> TranscriptionResult:
        """
        Unified transcription method that handles all processing types.

        Args:
            audio_path: Path to audio file
            progress_callback: Optional callback for progress updates
            **kwargs: Additional arguments passed to engines

        Returns:
            TranscriptionResult with comprehensive metadata
        """

        self.logger.info(f"Starting transcription: {audio_path}")
        overall_start = time.time()

        try:
            result = self._transcribe_standard(audio_path, progress_callback, **kwargs)

            total_time = time.time() - overall_start
            result.processing_time = total_time

            self.logger.info(f"Transcription completed in {total_time:.2f}s")
            self.perf_logger.log_metric("total_processing_time", total_time, "seconds")

            return result

        except Exception as e:
            self.logger.error(f"Transcription failed: {str(e)}")
            raise

    def _transcribe_standard(self,
                           audio_path: str,
                           progress_callback: Optional[Callable],
                           **kwargs) -> TranscriptionResult:
        """Perform standard transcription."""
        if progress_callback:
            progress_callback("Starting transcription...")

        result = self.transcription_engine.transcribe(audio_path, progress_callback=progress_callback, **kwargs)

        if progress_callback:
            progress_callback("Transcription completed")

        return result
