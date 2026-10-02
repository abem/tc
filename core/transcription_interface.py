"""
Unified transcription interface(ファサード)。

UnifiedTranscriber と、分割後の各モジュールの公開名の再 export を提供する。
従来どおり `from core.transcription_interface import UnifiedTranscriber,
Qwen3ASREngine, WhisperTranscriptionEngine, TranscriptionResult, ...` が使える。

構成:
- core.transcription_types: TranscriptionSegment / TranscriptionResult / TranscriptionEngine
- core.whisper_engine / core.whisper_text: Whisper エンジンとテキスト整形
- core.qwen3_engine / core.qwen3_chunking / core.qwen3_text: Qwen3-ASR エンジン
- core.nemotron_engine: Nemotron サブプロセスエンジン
- core.engine_factory: モデル名によるエンジン選択

警告抑制は suppress_warnings.py に一元化(各エントリポイントで import 済)。
このモジュール内では個別の filterwarnings を持たない。
"""

import time
from typing import Callable, Optional

from core.config import TranscriptionConfig
from core.engine_factory import create_engine
from core.logging import UnifiedLogger, PerformanceLogger
from core.qwen3_engine import Qwen3ASREngine
from core.transcription_types import (
    TranscriptionEngine,
    TranscriptionResult,
    TranscriptionSegment,
)
from core.whisper_engine import WhisperTranscriptionEngine

__all__ = [
    "TranscriptionSegment",
    "TranscriptionResult",
    "TranscriptionEngine",
    "WhisperTranscriptionEngine",
    "Qwen3ASREngine",
    "UnifiedTranscriber",
]


class UnifiedTranscriber:
    """Unified transcription interface that handles all transcription types."""
    
    def __init__(self,
                 transcription_config: TranscriptionConfig):
        self.transcription_config = transcription_config

        self.logger = UnifiedLogger.get_logger(self.__class__.__name__)
        self.perf_logger = PerformanceLogger(self.__class__.__name__)

        # エンジン選択(モデル名による nemotron -> qwen3-asr -> whisper の判定)は
        # core.engine_factory に集約している。
        self.transcription_engine = create_engine(transcription_config)

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
