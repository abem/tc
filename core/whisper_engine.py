"""
Whisper ベースの文字起こしエンジン。

テキスト整形([MM:SS] の解析・付与など)は core.whisper_text に委譲する。
"""

from typing import Callable, List, Optional
from pathlib import Path

import torch

from core.config import TranscriptionConfig
from core.progress import emit_progress
from core.transcription_types import (
    TranscriptionEngine,
    TranscriptionResult,
    TranscriptionSegment,
)
from core.utils import DEFAULT_AUDIO_DURATION_SEC, get_audio_duration
from core.whisper_text import (
    add_timestamps_to_text,
    create_chunks,
    ensure_timestamps_at_line_start,
    parse_timestamped_text,
)

__all__ = ["WhisperTranscriptionEngine"]


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
        return parse_timestamped_text(
            text, self.config.language, self._get_audio_duration_fallback()
        )

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
        return create_chunks(audio, chunk_size)

    def _add_timestamps_to_text(self, text: str, start_seconds: int) -> str:
        """Add timestamps to text segments."""
        return add_timestamps_to_text(text, start_seconds)

    def _ensure_timestamps_at_line_start(self, text: str) -> str:
        """Ensure timestamps are at the beginning of lines."""
        return ensure_timestamps_at_line_start(text)
