"""
OOP Design Patterns Package for transcribe_audio codebase optimization.

This package provides comprehensive Object-Oriented design pattern implementations
to improve the maintainability, testability, and extensibility of the transcribe_audio system.

Implemented Patterns:
- Abstract Factory: Model creation and configuration management
- Strategy Pattern: Batch optimization, timestamp formatting, processing strategies
- Command Pattern: Decoupled CLI operations and business logic
- Observer Pattern: Progress monitoring and event notifications
- Dependency Injection: Flexible service management
- Refactored Components: Breaking down God classes into focused components
- Utility Classes: Common functionality to eliminate code duplication

Usage:
    from patterns import factories, strategies, commands, observers
    from patterns.integration_example import TranscriptionService
    
    # Create complete service with all patterns
    service = TranscriptionService()
    results = service.transcribe_with_all_patterns(
        audio_path='audio.wav',
        language='ja',
        enable_diarization=True
    )
"""

# Version information
__version__ = "1.0.0"
__author__ = "Claude Code Assistant"
__description__ = "OOP Design Patterns for transcribe_audio optimization"

# Import main pattern modules
from . import factories
from . import strategies
from . import commands
from . import observers
from . import dependency_injection
from . import refactored_components
from . import utilities
from . import monitoring
from . import performance_integration

# Convenience imports for common use cases
from .factories import (
    ModelFactoryRegistry,
    ConfigurationFactory,
    create_japanese_transcriber,
    create_complete_processing_pipeline
)

from .strategies import (
    StrategyRegistry,
    AdaptiveBatchSizeStrategy,
    ElapsedTimeStrategy,
    SequentialProcessingStrategy
)

from .commands import (
    CommandInvoker,
    AudioProcessingContext,
    AudioProcessingPipeline
)

from .observers import (
    ObserverManager,
    setup_standard_monitoring,
    EventType,
    Event
)

from .dependency_injection import (
    create_default_container,
    ServiceLocator
)

from .refactored_components import (
    RefactoredWhisperTranscriber,
    ModelManager,
    AudioProcessor,
    MemoryManager
)

from .utilities import (
    FileValidator,
    TimestampUtils,
    PerformanceTimer,
    TemporaryFileManager,
    ErrorHandler,
    create_logger
)

from .monitoring import (
    PerformanceProfiler,
    SystemMetrics,
    ProcessMetrics,
    BottleneckInfo,
    monitor_transcription_performance
)

from .performance_integration import (
    PerformanceOptimizedTranscriber,
    PerformanceAwareConfig,
    create_performance_aware_transcriber,
    performance_monitoring_context
)

# Package-level convenience functions
def create_optimized_transcriber(
    language: str = 'ja',
    quality: str = 'balanced',
    enable_monitoring: bool = True
):
    """
    Create fully optimized transcriber using all patterns.
    
    Args:
        language: Target language for transcription
        quality: Quality preference ('fast', 'balanced', 'high_quality')
        enable_monitoring: Enable observer pattern monitoring
    
    Returns:
        Tuple of (transcriber, observers) if monitoring enabled, else just transcriber
    """
    # Factory pattern for model creation
    transcriber = create_japanese_transcriber(quality) if language == 'ja' else create_complete_processing_pipeline(language, False, quality)[0]
    
    # Strategy pattern for optimization
    batch_strategy = AdaptiveBatchSizeStrategy()
    timestamp_strategy = ElapsedTimeStrategy()
    
    # Refactored components
    optimized_transcriber = RefactoredWhisperTranscriber(
        model_name=transcriber.model_name if hasattr(transcriber, 'model_name') else 'openai/whisper-large-v3',
        batch_strategy=batch_strategy,
        timestamp_strategy=timestamp_strategy
    )
    
    if enable_monitoring:
        # Observer pattern for monitoring
        observable_transcriber, observers = setup_standard_monitoring(optimized_transcriber)
        return observable_transcriber, observers
    
    return optimized_transcriber


def process_audio_with_patterns(
    audio_path: str,
    output_path: str = None,
    language: str = 'ja',
    enable_diarization: bool = False,
    quality: str = 'balanced'
) -> dict:
    """
    Process audio using all implemented patterns for maximum optimization.
    
    This function demonstrates the complete integration of all OOP patterns:
    - Factory pattern for model creation
    - Strategy pattern for processing optimization  
    - Command pattern for operation orchestration
    - Observer pattern for progress monitoring
    - Dependency injection for service management
    - Utility classes for common operations
    
    Args:
        audio_path: Path to input audio file
        output_path: Path for output file (optional)
        language: Target language ('ja', 'en', etc.)
        enable_diarization: Enable speaker diarization
        quality: Quality preference
    
    Returns:
        Dictionary with transcription results and metrics
    """
    from .integration_example import TranscriptionService
    
    service = TranscriptionService()
    return service.transcribe_with_all_patterns(
        audio_path=audio_path,
        language=language,
        enable_diarization=enable_diarization,
        quality=quality,
        output_path=output_path
    )


# Pattern registry for dynamic access
AVAILABLE_PATTERNS = {
    'factory': 'Abstract Factory Pattern for model creation',
    'strategy': 'Strategy Pattern for flexible algorithms',
    'command': 'Command Pattern for decoupled operations',
    'observer': 'Observer Pattern for event notifications',
    'dependency_injection': 'Dependency Injection for service management',
    'refactored_components': 'Refactored components following SRP',
    'utilities': 'Utility classes for common operations'
}


def get_pattern_info() -> dict:
    """Get information about all implemented patterns."""
    return {
        'version': __version__,
        'patterns': AVAILABLE_PATTERNS,
        'benefits': [
            'Improved maintainability through separation of concerns',
            'Enhanced testability with dependency injection',
            'Better extensibility via strategy and factory patterns',
            'Reduced code duplication with utility classes',
            'Real-time monitoring through observer pattern',
            'Flexible operation orchestration via command pattern'
        ],
        'usage': 'Import patterns modules or use convenience functions'
    }


# Module initialization
import logging
logging.getLogger(__name__).info(f"OOP Patterns package initialized (v{__version__})")

__all__ = [
    # Modules
    'factories',
    'strategies', 
    'commands',
    'observers',
    'dependency_injection',
    'refactored_components',
    'utilities',
    'monitoring',
    'performance_integration',
    
    # Main classes
    'ModelFactoryRegistry',
    'ConfigurationFactory',
    'StrategyRegistry',
    'CommandInvoker',
    'ObserverManager',
    'ServiceLocator',
    'RefactoredWhisperTranscriber',
    'ModelManager',
    'AudioProcessor',
    'MemoryManager',
    'FileValidator',
    'TimestampUtils',
    'PerformanceTimer',
    
    # Performance monitoring classes
    'PerformanceProfiler',
    'SystemMetrics',
    'ProcessMetrics',
    'BottleneckInfo',
    'PerformanceOptimizedTranscriber',
    'PerformanceAwareConfig',
    
    # Convenience functions
    'create_optimized_transcriber',
    'process_audio_with_patterns',
    'get_pattern_info',
    'monitor_transcription_performance',
    'create_performance_aware_transcriber',
    'performance_monitoring_context',
    
    # Constants
    'AVAILABLE_PATTERNS'
]