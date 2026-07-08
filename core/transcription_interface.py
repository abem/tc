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
        """Qwen3ASRModel を遅延ロード。"""
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

    def transcribe(self, audio_path: str, **kwargs) -> TranscriptionResult:
        """Qwen3-ASR で文字起こし。"""
        self.validate_audio_file(audio_path)

        start_time = time.time()
        self.perf_logger.start_timing(f"transcribe_{Path(audio_path).name}")

        try:
            self._load_model()

            # 言語マップ (TranscriptionConfig.language -> Qwen3 の言語名)
            lang_map = {"ja": "Japanese", "en": "English"}
            language = lang_map.get(self.config.language, None)

            results = self._model.transcribe(
                audio=str(audio_path),
                language=language,
                # タイムスタンプ取得には forced_aligner モデルの別途ロードが必要なため、
                # デフォルトでは無効。forced_aligner を初期化時に渡した場合のみ有効化可能。
                return_time_stamps=False,
            )

            processing_time = self.perf_logger.end_timing(f"transcribe_{Path(audio_path).name}")

            if not results:
                raise RuntimeError("Qwen3-ASR returned no results")

            r = results[0]
            detected_language = self._language_name_to_code(r.language or self.config.language)
            text = r.text.strip()
            segments = self._results_to_segments(r, detected_language)

            result = TranscriptionResult(
                text=text,
                segments=segments,
                language=detected_language,
                duration=self._get_audio_duration(audio_path),
                processing_time=processing_time,
                model_name=self.config.model,
                has_speakers=False,
                metadata={"detected_language": r.language},
            )

            self.logger.info(f"Transcription completed: {len(text)} characters")
            return result

        except Exception as e:
            self.logger.error(f"Transcription failed: {str(e)}")
            raise

    def _results_to_segments(self, result, language: str) -> List[TranscriptionSegment]:
        """Qwen3-ASR の結果を TranscriptionSegment に変換。"""
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
                end=self._get_audio_duration_fallback(),
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