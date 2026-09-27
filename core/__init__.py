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
    get_logger
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
        get_global_model_manager,
        configure_model_manager
    )
    _model_manager_available = True
except ImportError:
    UnifiedModelManager = None
    get_global_model_manager = None
    configure_model_manager = None

try:
    from .transcription_interface import (
        UnifiedTranscriber,
        TranscriptionResult,
        TranscriptionSegment,
        create_transcriber,
        create_japanese_transcriber,
        create_english_transcriber
    )
    _transcription_available = True
except ImportError:
    UnifiedTranscriber = None
    TranscriptionResult = None
    TranscriptionSegment = None
    create_transcriber = None
    create_japanese_transcriber = None
    create_english_transcriber = None

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

    # Utils
    "is_youtube_url",
    "is_google_drive_url",
    "extract_gdrive_file_id",
    "detect_input_type",
    "resolve_device",

    # Model Management (optional)
    "UnifiedModelManager",
    "get_global_model_manager",
    "configure_model_manager",

    # Transcription (optional)
    "UnifiedTranscriber",
    "TranscriptionResult",
    "TranscriptionSegment",
    "create_transcriber",
    "create_japanese_transcriber",
    "create_english_transcriber"
]

# Initialize logging system
#
# pytest実行時は本番ログファイル(logs/transcription.log)へ書き込まない
# (tc-ops #548是正、2026-09-27)。core.__init__は`import core`されるだけで
# 無条件にこのUnifiedLogger.configure()を実行する副作用を持つため、テスト実行時にも
# 本番ログへテスト由来の行が混入していた。"pytest" in sys.modules はpytest実行時に
# 必ずTrueになる(pytest自身がインポートされて実行されているため)標準的な判定方法。
# テスト時のログ出力先は既存パターン(core/logging.py L188、__main__ブロックの
# logs/transcription_test.log)に倣う。
import sys as _sys

_TRANSCRIPTION_LOG_FILE = (
    "logs/transcription_test.log" if "pytest" in _sys.modules else "logs/transcription.log"
)

UnifiedLogger.configure(
    log_level="INFO",
    log_file=_TRANSCRIPTION_LOG_FILE,
    enable_console=True,
    enable_file=True
)

# Get logger for this module
logger = UnifiedLogger.get_logger(__name__)
logger.info(f"Core unified modules initialized (v{__version__})")
if not _model_manager_available:
    logger.info("Model manager modules not available (missing optional dependencies).")
if not _transcription_available:
    logger.info("Transcription modules not available (missing optional dependencies).")
