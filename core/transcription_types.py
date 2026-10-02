"""
文字起こしの型と抽象基底クラス(TranscriptionSegment / TranscriptionResult /
TranscriptionEngine)。

各エンジン(Whisper / Qwen3 / Nemotron)とファサード(UnifiedTranscriber)が
共通で依存する最下層のモジュール。他の core.* エンジンモジュールを import
しないため、エンジン間の循環 import を構造的に防ぐ。
公開名は `core.transcription_interface` からも再 export される。
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.config import TranscriptionConfig
from core.logging import UnifiedLogger, PerformanceLogger
from core.model_manager import get_global_model_manager

__all__ = ["TranscriptionSegment", "TranscriptionResult", "TranscriptionEngine"]


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
