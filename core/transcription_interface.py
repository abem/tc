"""
Unified transcription interface.
Consolidates all transcribe() method implementations into a single, consistent API.

警告抑制は suppress_warnings.py に一元化(各エントリポイントで import 済)。
このモジュール内では個別の filterwarnings を持たない。
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Union, Callable
from dataclasses import dataclass
import time
from pathlib import Path
import torch

from core.config import TranscriptionConfig, DiarizationConfig
from core.logging import UnifiedLogger, PerformanceLogger
from core.model_manager import get_global_model_manager


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
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "text": self.text,
            "segments": [
                {
                    "start": seg.start,
                    "end": seg.end,
                    "text": seg.text,
                    "speaker": seg.speaker,
                    "confidence": seg.confidence,
                    "language": seg.language
                }
                for seg in self.segments
            ],
            "language": self.language,
            "duration": self.duration,
            "processing_time": self.processing_time,
            "model_name": self.model_name,
            "has_speakers": self.has_speakers,
            "metadata": self.metadata or {}
        }


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
    
    def _create_segments_from_result(self, 
                                   raw_result: Dict[str, Any],
                                   has_speakers: bool = False) -> List[TranscriptionSegment]:
        """Convert raw transcription result to structured segments."""
        segments = []
        
        if "segments" in raw_result:
            for seg_data in raw_result["segments"]:
                segment = TranscriptionSegment(
                    start=seg_data.get("start", 0.0),
                    end=seg_data.get("end", 0.0),
                    text=seg_data.get("text", ""),
                    speaker=seg_data.get("speaker") if has_speakers else None,
                    confidence=seg_data.get("confidence"),
                    language=seg_data.get("language", self.config.language)
                )
                segments.append(segment)
        
        return segments


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
        
        start_time = time.time()
        self.perf_logger.start_timing(f"transcribe_{Path(audio_path).name}")
        
        try:
            # Load model
            self._load_model()
            
            # Get full transcription with original functionality
            full_text = self._transcribe_with_original_logic(audio_path)
            
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
        return 600.0  # Default 10 minutes
    
    def _load_audio(self, audio_path: str):
        """Load audio file for processing."""
        import librosa
        audio, _ = librosa.load(audio_path, sr=16000)
        return audio
    
    def _get_audio_duration(self, audio_path: str) -> float:
        """Get audio file duration."""
        import librosa
        try:
            audio, sr = librosa.load(audio_path, sr=None)
            return len(audio) / sr
        except:
            return self._get_audio_duration_fallback()
    
    def _transcribe_with_original_logic(self, audio_path: str) -> str:
        """Transcribe using the original WhisperTranscriber logic for quality."""
        import soundfile as sf
        import numpy as np
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
            except (ImportError, Exception) as e:
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
            from qwen_asr import Qwen3ASRModel
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

    # 長音声を分割する閾値(秒)。
    # 実測で10分(600s)までは成功、15分(900s)で CUBLAS_STATUS_INTERNAL_ERROR が
    # 発生することを確認(RTX 4080 SUPER / torch 2.11.0+cu130 / bfloat16)。
    # Windows 側を含むシステム全体の GPU 負荷ピークを抑えるため、
    # 安全側に振って 5 分(300s)をチャンク上限とする(実測で成功済み)。
    CHUNK_THRESHOLD_SEC = 300

    def transcribe(self, audio_path: str, **kwargs) -> TranscriptionResult:
        """Qwen3-ASR で文字起こし。長音声は自動的に分割して処理。"""
        self.validate_audio_file(audio_path)

        start_time = time.time()
        self.perf_logger.start_timing(f"transcribe_{Path(audio_path).name}")

        try:
            self._load_model()

            # 言語マップ (TranscriptionConfig.language -> Qwen3 の言語名)
            lang_map = {"ja": "Japanese", "en": "English"}
            language = lang_map.get(self.config.language, None)

            duration = self._get_audio_duration(audio_path)
            failed_chunks = 0
            repeated_chunks = 0
            if duration > self.CHUNK_THRESHOLD_SEC:
                # 長音声: 分割して処理
                self.logger.info(
                    f"Audio is {duration:.0f}s (>{self.CHUNK_THRESHOLD_SEC}s), "
                    f"splitting into chunks for stable processing"
                )
                text, detected_language, failed_chunks, repeated_chunks = self._transcribe_long_audio(
                    audio_path, duration, language, self.config.context
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
                # 文節改行フォーマットを適用
                text = self._format_text_with_breaks(r.text.strip())

            processing_time = self.perf_logger.end_timing(f"transcribe_{Path(audio_path).name}")

            # 結果を構築(segments は全体を1セグメントとして扱う)
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
                },
            )

            self.logger.info(f"Transcription completed: {len(text)} characters")
            return result

        except Exception as e:
            self.logger.error(f"Transcription failed: {str(e)}")
            raise

    def _transcribe_long_audio(self, audio_path: str, duration: float, language: Optional[str], context: str = ""):
        """長音声を CHUNK_THRESHOLD_SEC 毎に分割して文字起こし、結果を結合する。

        Qwen3-ASR の内部チャンク処理でも長音声に対応しているが、
        RTX 4080 SUPER + torch 2.11.0+cu130 環境で15分超の音声で
        CUBLAS_STATUS_INTERNAL_ERROR が発生するため、外部で分割する。
        分割は音声ファイルを物理的に切り出すのではなく、(np.ndarray, sr)
        タプルを渡してメモリ上で処理する。

        各チャンクの生テキストを結合してから最後に1回だけ文節改行を適用する。
        (チャンク毎にフォーマットすると境界の文節が分断されるため)

        戻り値: (結合テキスト, 検出言語コード, 失敗チャンク数, 反復検出チャンク数)
        チャンクが失敗した場合は結果テキストに [チャンクN失敗] プレースホルダを
        挿入し、ユーザーが欠落に気づけるようにする。反復ループを検出した
        チャンクは1回だけ再試行し、再試行後も反復する場合は
        [チャンクN反復検出のため破棄] プレースホルダを挿入する。
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

        for i in tqdm(range(total_chunks), desc="音声文字起こし(分割)"):
            start_sample = i * chunk_samples
            end_sample = min(start_sample + chunk_samples, len(audio))
            chunk = audio[start_sample:end_sample]

            if len(chunk) < sr:  # 1秒未満の端数はスキップ
                continue

            chunk_start_time = time.time()
            try:
                results = self._model.transcribe(
                    audio=(chunk, sr),
                    context=context,
                    language=language,
                    return_time_stamps=False,
                )
                if results:
                    r = results[0]
                    chunk_text = r.text.strip()

                    # 反復ループ検出(bugfix 2026-08-03): 同一文/単語がチャンク末尾まで
                    # 異常反復し意味的に破壊される事象への事後対策。予防策
                    # (generation_config、_load_model参照)を適用済みでも反復に
                    # 至った場合の安全網として、1回だけ同一チャンクを再試行する。
                    if chunk_text and self._detect_repetition(chunk_text):
                        repeated_chunks += 1
                        self.logger.warning(
                            f"Chunk {i+1}/{total_chunks}: repetition loop detected "
                            f"({len(chunk_text)} chars), retrying once"
                        )
                        retry_results = self._model.transcribe(
                            audio=(chunk, sr),
                            context=context,
                            language=language,
                            return_time_stamps=False,
                        )
                        retry_text = retry_results[0].text.strip() if retry_results else ""
                        if retry_text and not self._detect_repetition(retry_text):
                            self.logger.info(f"Chunk {i+1}/{total_chunks}: retry succeeded")
                            r = retry_results[0]
                            chunk_text = retry_text
                        else:
                            self.logger.warning(
                                f"Chunk {i+1}/{total_chunks}: retry still repetitive, discarding chunk"
                            )
                            chunk_text = f"\n[チャンク{i+1}反復検出のため破棄]\n"

                    if chunk_text:
                        raw_texts.append(chunk_text)
                    # 最初のチャンクの検出言語を使う
                    if i == 0 and r.language:
                        detected_lang = self._language_name_to_code(r.language)

                chunk_elapsed = time.time() - chunk_start_time
                self.logger.info(
                    f"Chunk {i+1}/{total_chunks} done in {chunk_elapsed:.1f}s "
                    f"(lang={detected_lang})"
                )
            except Exception as e:
                failed_chunks += 1
                self.logger.warning(f"Chunk {i+1}/{total_chunks} failed: {e}, inserting placeholder")
                # プレースホルダは前後で改行を強制(自然文ではないため)
                raw_texts.append(f"\n[チャンク{i+1}失敗]\n")
                continue

        # 生テキストを全チャンク結合してから、最後に1回だけ文節改行を適用
        # (チャンク毎にフォーマットすると境界の文節が分断されるため)
        raw_text = "".join(raw_texts)
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
        return text, detected_lang, failed_chunks, repeated_chunks

    @staticmethod
    def _detect_repetition(text: str, max_cycle: int = 40, min_repeats: int = 3) -> bool:
        """句読点区切りの文節列に、同一の文節シーケンス(長さ1〜max_cycle)が
        min_repeats回以上連続して繰り返される箇所がないかを検出する。

        ASRの反復ループ(実障害: 「アジェンツは、ツールコールの高品質と正確さを
        必要とするため...」という1文が単語単位の改行を伴い70回以上連続反復)を
        検知するための軽量ヒューリスティック。正規表現の後方参照
        (`(.+)\\1{2,}`)はバックトラック爆発のリスクがあるため使わず、
        文節リストに対する固定長スライド窓比較で実装する。
        """
        import re

        fragments = [s for s in re.split(r'(?<=[。、！？!?])', text) if s.strip()]
        n = len(fragments)
        if n < min_repeats:
            return False

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
                    return True
        return False

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

    def _results_to_segments(self, result, language: str, audio_path: str) -> List[TranscriptionSegment]:
        """Qwen3-ASR の結果を TranscriptionSegment に変換。

        return_time_stamps=False(デフォルト)の場合は time_stamps が None になるため、
        フォールバックで音声全体を1セグメントとする。この際 segment.end には
        _get_audio_duration_fallback() の固定値(600s)ではなく、実音声長を使う。
        """
        segments = []
        if getattr(result, "time_stamps", None):
            for ts in result.time_stamps:
                segments.append(TranscriptionSegment(
                    start=ts.start_time,
                    end=ts.end_time,
                    text=ts.text,
                    language=language,
                ))
        if not segments and result.text.strip():
            segments = [TranscriptionSegment(
                start=0.0,
                end=self._get_audio_duration(audio_path),
                text=result.text.strip(),
                language=language,
            )]
        return segments

    @staticmethod
    def _language_name_to_code(name: Optional[str]) -> str:
        """'Japanese' -> 'ja' のように言語名をコードに変換。"""
        mapping = {"japanese": "ja", "english": "en"}
        return mapping.get((name or "").lower(), name or "ja")

    @staticmethod
    def _get_audio_duration_fallback() -> float:
        """音声長取得失敗時のフォールバック。"""
        return 600.0  # デフォルト 10 分

    def _get_audio_duration(self, audio_path: str) -> float:
        """音声ファイルの長さを取得。"""
        import soundfile as sf
        try:
            info = sf.info(audio_path)
            return info.duration
        except Exception:
            return self._get_audio_duration_fallback()


class UnifiedTranscriber:
    """Unified transcription interface that handles all transcription types."""
    
    def __init__(self, 
                 transcription_config: TranscriptionConfig,
                 diarization_config: Optional[DiarizationConfig] = None):
        self.transcription_config = transcription_config
        self.diarization_config = diarization_config
        
        self.logger = UnifiedLogger.get_logger(self.__class__.__name__)
        self.perf_logger = PerformanceLogger(self.__class__.__name__)
        
        # Initialize engines
        # モデル名でエンジンを切替(Qwen3-ASR 系は専用エンジン、それ以外は Whisper)
        if Qwen3ASREngine.is_qwen3_model(transcription_config.model):
            self.transcription_engine = Qwen3ASREngine(transcription_config)
        else:
            self.transcription_engine = WhisperTranscriptionEngine(transcription_config)
        self.diarization_engine = None
        
        if diarization_config and diarization_config.enable_diarization:
            self._initialize_diarization()
    
    def _initialize_diarization(self):
        """Initialize speaker diarization if enabled."""
        try:
            from core.diarization_engine import DiarizationEngine
            self.diarization_engine = DiarizationEngine(self.diarization_config)
        except ImportError:
            self.logger.warning("Diarization dependencies not available")
    
    def transcribe(self, 
                   audio_path: str, 
                   enable_diarization: Optional[bool] = None,
                   progress_callback: Optional[Callable] = None,
                   **kwargs) -> TranscriptionResult:
        """
        Unified transcription method that handles all processing types.
        
        Args:
            audio_path: Path to audio file
            enable_diarization: Override diarization setting
            progress_callback: Optional callback for progress updates
            **kwargs: Additional arguments passed to engines
            
        Returns:
            TranscriptionResult with comprehensive metadata
        """
        
        self.logger.info(f"Starting transcription: {audio_path}")
        overall_start = time.time()
        
        # Determine if diarization should be used
        use_diarization = (
            enable_diarization if enable_diarization is not None
            else (self.diarization_config and self.diarization_config.enable_diarization)
        )
        
        try:
            if use_diarization and self.diarization_engine:
                # Transcription with speaker diarization
                result = self._transcribe_with_speakers(audio_path, progress_callback, **kwargs)
            else:
                # Standard transcription
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
        """Perform standard transcription without speaker diarization."""
        if progress_callback:
            progress_callback("Starting transcription...")
        
        result = self.transcription_engine.transcribe(audio_path, **kwargs)
        
        if progress_callback:
            progress_callback("Transcription completed")
        
        return result
    
    def _transcribe_with_speakers(self, 
                                audio_path: str, 
                                progress_callback: Optional[Callable],
                                **kwargs) -> TranscriptionResult:
        """Perform transcription with speaker diarization."""
        if progress_callback:
            progress_callback("Starting diarization...")
        
        # Perform diarization first
        speaker_segments = self.diarization_engine.diarize(audio_path)
        
        if progress_callback:
            progress_callback("Diarization completed, starting transcription...")
        
        # Transcribe each speaker segment
        all_segments = []
        full_text_parts = []
        
        for speaker_seg in speaker_segments:
            # Extract audio segment for this speaker
            segment_audio_path = self._extract_audio_segment(
                audio_path, speaker_seg.start, speaker_seg.end
            )
            
            # Transcribe segment
            segment_result = self.transcription_engine.transcribe(segment_audio_path)
            
            # Add speaker information
            for seg in segment_result.segments:
                seg.speaker = speaker_seg.speaker
                seg.start += speaker_seg.start  # Adjust timing
                seg.end += speaker_seg.start
                all_segments.append(seg)
                full_text_parts.append(f"[{seg.speaker}] {seg.text}")
        
        if progress_callback:
            progress_callback("Transcription with speakers completed")
        
        # Create unified result
        result = TranscriptionResult(
            text="\n".join(full_text_parts),
            segments=sorted(all_segments, key=lambda x: x.start),
            language=self.transcription_config.language,
            duration=self._get_audio_duration(audio_path),
            processing_time=0.0,  # Will be set by caller
            model_name=self.transcription_config.model,
            has_speakers=True
        )
        
        return result
    
    def _extract_audio_segment(self, audio_path: str, start: float, end: float) -> str:
        """Extract audio segment for speaker-specific transcription."""
        # This would typically use ffmpeg or similar
        # For now, return original path (implementation needed)
        return audio_path
    
    def _get_audio_duration(self, audio_path: str) -> float:
        """Get audio file duration."""
        import soundfile as sf
        audio, sr = sf.read(audio_path)
        return len(audio) / sr
    
    def get_stats(self) -> Dict[str, Any]:
        """Get transcription system statistics."""
        stats = {
            "transcription_engine": self.transcription_engine.get_engine_name(),
            "diarization_enabled": self.diarization_engine is not None,
            "model_cache_stats": self.transcription_engine.model_manager.get_cache_stats()
        }
        
        if self.diarization_engine:
            stats["diarization_engine"] = "pyannote"
        
        return stats


# Factory functions for backward compatibility
def create_transcriber(config: TranscriptionConfig, 
                      diarization_config: Optional[DiarizationConfig] = None) -> UnifiedTranscriber:
    """Create a unified transcriber with the specified configuration."""
    return UnifiedTranscriber(config, diarization_config)


def create_japanese_transcriber(quality: str = "high") -> UnifiedTranscriber:
    """Create a transcriber optimized for Japanese."""
    config = TranscriptionConfig.for_language("ja", quality)
    return UnifiedTranscriber(config)


def create_english_transcriber(quality: str = "high") -> UnifiedTranscriber:
    """Create a transcriber optimized for English."""
    config = TranscriptionConfig.for_language("en", quality)
    return UnifiedTranscriber(config)


# Testing
if __name__ == "__main__":
    from core.config import TranscriptionConfig
    
    config = TranscriptionConfig.for_language("ja", "high")
    transcriber = UnifiedTranscriber(config)
    
    print(f"Transcriber created: {transcriber.get_stats()}")