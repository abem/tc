"""
Core unified modules for the transcription system.
This package consolidates all configuration, logging, model management,
and transcription interfaces into a single, consistent API.
"""

from .config import (
    TranscriptionConfig,
    SystemConfig,
    UnifiedConfig
)

from .logging import (
    UnifiedLogger,
    PerformanceLogger,
    get_logger,
    setup_logging
)

from .utils import (
    is_youtube_url,
    is_google_drive_url,
    extract_gdrive_file_id,
    detect_input_type,
    resolve_device
)

_model_manager_available = False
_transcription_available = False

try:
    from .model_manager import (
        UnifiedModelManager,
        get_global_model_manager
    )
    _model_manager_available = True
except ImportError:
    UnifiedModelManager = None
    get_global_model_manager = None

try:
    from .transcription_interface import (
        UnifiedTranscriber,
        TranscriptionResult,
        TranscriptionSegment
    )
    _transcription_available = True
except ImportError:
    UnifiedTranscriber = None
    TranscriptionResult = None
    TranscriptionSegment = None

__version__ = "2025.07.29-unified"
__all__ = [
    # Config
    "TranscriptionConfig",
    "SystemConfig",
    "UnifiedConfig",

    # Logging
    "UnifiedLogger",
    "PerformanceLogger",
    "get_logger",
    "setup_logging",

    # Utils
    "is_youtube_url",
    "is_google_drive_url",
    "extract_gdrive_file_id",
    "detect_input_type",
    "resolve_device",

    # Model Management (optional)
    "UnifiedModelManager",
    "get_global_model_manager",

    # Transcription (optional)
    "UnifiedTranscriber",
    "TranscriptionResult",
    "TranscriptionSegment"
]

# ログ初期化は import 時には行わない(副作用なし)。
# エントリポイント(tc / transcribe.py / webui.py)が core.logging.setup_logging() を明示的に呼ぶ。
logger = UnifiedLogger.get_logger(__name__)
