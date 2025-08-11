"""
Core unified modules for the transcription system.
This package consolidates all configuration, logging, model management,
and transcription interfaces into a single, consistent API.
"""

from .config import (
    TranscriptionConfig,
    DiarizationConfig, 
    SystemConfig,
    UnifiedConfig
)

from .logging_config import (
    UnifiedLogger,
    PerformanceLogger,
    get_logger
)

from .model_manager import (
    UnifiedModelManager,
    get_global_model_manager,
    configure_model_manager
)

from .transcription_interface import (
    UnifiedTranscriber,
    TranscriptionResult,
    TranscriptionSegment,
    create_transcriber,
    create_japanese_transcriber,
    create_english_transcriber
)

__version__ = "2025.07.29-unified"
__all__ = [
    # Config
    "TranscriptionConfig",
    "DiarizationConfig", 
    "SystemConfig",
    "UnifiedConfig",
    
    # Logging
    "UnifiedLogger",
    "PerformanceLogger", 
    "get_logger",
    
    # Model Management
    "UnifiedModelManager",
    "get_global_model_manager",
    "configure_model_manager",
    
    # Transcription
    "UnifiedTranscriber",
    "TranscriptionResult",
    "TranscriptionSegment",
    "create_transcriber",
    "create_japanese_transcriber",
    "create_english_transcriber"
]

# Initialize logging system
UnifiedLogger.configure(
    log_level="INFO",
    log_file="logs/transcription.log",
    enable_console=True,
    enable_file=True
)

# Get logger for this module  
logger = UnifiedLogger.get_logger(__name__)
logger.info(f"Core unified modules initialized (v{__version__})")