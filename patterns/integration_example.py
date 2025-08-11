"""
Integration example demonstrating how to use all the OOP patterns together.
Shows how to combine Abstract Factory, Strategy, Command, Observer, and Dependency Injection patterns
for a complete, maintainable transcription system.
"""

import sys
from pathlib import Path
import logging

# Add patterns directory to Python path
sys.path.insert(0, str(Path(__file__).parent))

from factories import (
    ModelFactoryRegistry, ConfigurationFactory, ProcessingConfiguration,
    create_japanese_transcriber, create_complete_processing_pipeline
)
from strategies import (
    StrategyRegistry, create_device_info, create_audio_info,
    AdaptiveBatchSizeStrategy, ElapsedTimeStrategy, SequentialProcessingStrategy
)
from commands import (
    CommandInvoker, AudioProcessingContext, AudioProcessingPipeline,
    ValidateInputCommand, LoadConfigurationCommand, TranscribeAudioCommand
)
from observers import (
    ObserverManager, setup_standard_monitoring, get_metrics_from_observers,
    EventType, Event
)
from dependency_injection import (
    create_default_container, ServiceLocator, StorageHandler, LoggingHandler,
    ConfigurationProvider, inject
)
from refactored_components import (
    RefactoredWhisperTranscriber, ModelManager, AudioProcessor, MemoryManager
)
from utilities import (
    FileValidator, TimestampUtils, PerformanceTimer, TemporaryFileManager,
    ErrorHandler, create_logger
)


class TranscriptionService:
    """
    Complete transcription service demonstrating integration of all patterns.
    This shows how to use the patterns together in a real-world scenario.
    """
    
    def __init__(self):
        self.logger = create_logger('TranscriptionService')
        self.command_invoker = CommandInvoker()
        self.container = create_default_container()
        
        # Initialize service locator for dependency injection
        ServiceLocator.initialize(self.container)
        
        # Setup error handling
        self.error_handler = ErrorHandler(self.logger)
    
    def transcribe_with_all_patterns(
        self,
        audio_path: str,
        language: str = 'ja',
        enable_diarization: bool = False,
        quality: str = 'balanced',
        output_path: str = None
    ) -> dict:
        """
        Complete transcription pipeline using all implemented patterns.
        
        Demonstrates:
        - Abstract Factory for model creation
        - Strategy Pattern for batch optimization and timestamp formatting
        - Command Pattern for operation orchestration
        - Observer Pattern for progress monitoring
        - Dependency Injection for service management
        - Utility classes for common operations
        """
        
        results = {
            'success': False,
            'transcription': None,
            'metrics': {},
            'performance': {},
            'errors': []
        }
        
        with PerformanceTimer('Complete Transcription Pipeline', self.logger) as timer:
            try:
                # 1. Factory Pattern: Create processing configuration
                self.logger.info("Creating processing configuration using Factory Pattern")
                config = ProcessingConfiguration.create_for_language(
                    language=language,
                    enable_diarization=enable_diarization
                )
                
                # 2. Factory Pattern: Create transcriber and diarizer
                self.logger.info("Creating models using Factory Pattern")
                transcriber, diarizer = create_complete_processing_pipeline(
                    language=language,
                    enable_diarization=enable_diarization,
                    quality=quality
                )
                
                # 3. Strategy Pattern: Configure processing strategies
                self.logger.info("Setting up Strategy Pattern")
                batch_strategy = AdaptiveBatchSizeStrategy()
                timestamp_strategy = ElapsedTimeStrategy()
                processing_strategy = SequentialProcessingStrategy()
                
                # 4. Refactored Components: Create modern transcriber
                self.logger.info("Creating refactored transcriber components")
                modern_transcriber = RefactoredWhisperTranscriber(
                    model_name=config.transcription.model,
                    batch_strategy=batch_strategy,
                    timestamp_strategy=timestamp_strategy,
                    processing_strategy=processing_strategy
                )
                
                # 5. Observer Pattern: Setup monitoring
                self.logger.info("Setting up Observer Pattern for monitoring")
                observable_transcriber, observers = setup_standard_monitoring(modern_transcriber)
                
                # 6. Utility Classes: Validate input
                self.logger.info("Validating input using Utility classes")
                validation_result = FileValidator.validate_audio_file(audio_path)
                if not validation_result.is_valid:
                    raise ValueError(validation_result.error_message)
                
                # 7. Command Pattern: Execute transcription
                self.logger.info("Executing transcription using Command Pattern")
                processing_context = AudioProcessingContext(
                    input_path=audio_path,
                    output_path=output_path,
                    language=language,
                    enable_diarization=enable_diarization,
                    config=config
                )
                
                # Execute using command pattern
                result = self.command_invoker.execute_pipeline(processing_context)
                
                # 8. Alternative: Direct execution with observers
                self.logger.info("Executing with Observer monitoring")
                transcription_text = observable_transcriber.transcribe(audio_path)
                
                # 9. Utility Classes: Process results
                self.logger.info("Processing results using Utility classes")
                cleaned_text = self._process_transcription_results(transcription_text)
                
                # 10. Collect metrics from observers
                metrics = get_metrics_from_observers(observers)
                
                # 11. Performance statistics
                performance_stats = modern_transcriber.get_performance_stats()
                
                # Success!
                results.update({
                    'success': True,
                    'transcription': cleaned_text,
                    'metrics': metrics,
                    'performance': performance_stats,
                    'processing_time': timer.get_duration()
                })
                
                self.logger.info("Transcription completed successfully using all patterns")
                
            except Exception as e:
                self.logger.error(f"Transcription failed: {str(e)}", exc_info=True)
                results['errors'].append(str(e))
        
        return results
    
    def _process_transcription_results(self, transcription_text: str) -> str:
        """Process transcription results using utility classes."""
        from utilities import TextProcessingUtils
        
        # Clean the transcription text
        cleaned_text = TextProcessingUtils.clean_transcription_text(transcription_text)
        
        # Estimate reading time
        reading_time = TextProcessingUtils.estimate_reading_time(cleaned_text)
        
        # Add metadata
        metadata_header = f"# Transcription Results\n"
        metadata_header += f"Estimated reading time: {reading_time:.1f} minutes\n"
        metadata_header += f"Character count: {len(cleaned_text)}\n"
        metadata_header += f"Word count: {len(cleaned_text.split())}\n\n"
        
        return metadata_header + cleaned_text


def demonstrate_factory_pattern():
    """Demonstrate Abstract Factory Pattern usage."""
    print("\n=== Abstract Factory Pattern Demo ===")
    
    # Language-aware model creation
    japanese_transcriber = create_japanese_transcriber(quality='high_quality')
    print(f"Created Japanese transcriber: {type(japanese_transcriber).__name__}")
    
    # Complete pipeline creation
    transcriber, diarizer = create_complete_processing_pipeline(
        language='en',
        enable_diarization=True,
        quality='balanced'
    )
    print(f"Created English pipeline: {type(transcriber).__name__} + {type(diarizer).__name__ if diarizer else 'No diarizer'}")


def demonstrate_strategy_pattern():
    """Demonstrate Strategy Pattern usage."""
    print("\n=== Strategy Pattern Demo ===")
    
    # Different batch size strategies
    gpu_strategy = StrategyRegistry.get_batch_strategy('gpu', rtx_4080_optimized=True)
    cpu_strategy = StrategyRegistry.get_batch_strategy('cpu')
    adaptive_strategy = StrategyRegistry.get_batch_strategy('adaptive')
    
    print(f"GPU Strategy: {type(gpu_strategy).__name__}")
    print(f"CPU Strategy: {type(cpu_strategy).__name__}")
    print(f"Adaptive Strategy: {type(adaptive_strategy).__name__}")
    
    # Different timestamp strategies
    elapsed_strategy = StrategyRegistry.get_timestamp_strategy('elapsed')
    ms_strategy = StrategyRegistry.get_timestamp_strategy('milliseconds')
    
    sample_time = 125.750
    print(f"Elapsed format: {elapsed_strategy.format_timestamp(sample_time)}")
    print(f"Milliseconds format: {ms_strategy.format_timestamp(sample_time)}")


def demonstrate_command_pattern():
    """Demonstrate Command Pattern usage."""
    print("\n=== Command Pattern Demo ===")
    
    # Create sample audio path (for demo purposes)
    sample_audio = "/path/to/sample.wav"
    
    # Individual commands
    validate_cmd = ValidateInputCommand(sample_audio)
    print(f"Created validation command: {type(validate_cmd).__name__}")
    
    # Processing context
    context = AudioProcessingContext(
        input_path=sample_audio,
        language='ja',
        enable_diarization=False
    )
    
    # Command pipeline
    pipeline = AudioProcessingPipeline.create_full_pipeline(context)
    print(f"Created processing pipeline with {len(pipeline.commands)} commands")


def demonstrate_observer_pattern():
    """Demonstrate Observer Pattern usage."""
    print("\n=== Observer Pattern Demo ===")
    
    # Create observers
    console_observer = ObserverManager.create_console_observer()
    logging_observer = ObserverManager.create_logging_observer()
    metrics_observer = ObserverManager.create_metrics_observer()
    
    print(f"Created observers: {[type(obs).__name__ for obs in [console_observer, logging_observer, metrics_observer]]}")
    
    # Simulate events
    from observers import Event, EventType
    
    sample_event = Event(
        event_type=EventType.PROGRESS_UPDATE,
        message="Processing audio chunks",
        progress=0.5,
        source="DemoTranscriber"
    )
    
    # Update observers
    for observer in [console_observer, logging_observer, metrics_observer]:
        observer.update(sample_event)
    
    print("Observers updated with sample event")


def demonstrate_dependency_injection():
    """Demonstrate Dependency Injection usage."""
    print("\n=== Dependency Injection Demo ===")
    
    # Create DI container
    container = create_default_container()
    
    # Resolve services
    storage_service = container.resolve(StorageHandler)
    logging_service = container.resolve(LoggingHandler)
    config_service = container.resolve(ConfigurationProvider)
    
    print(f"Resolved services:")
    print(f"  Storage: {type(storage_service).__name__}")
    print(f"  Logging: {type(logging_service).__name__}")
    print(f"  Config: {type(config_service).__name__}")
    
    # Service locator usage
    ServiceLocator.initialize(container)
    resolved_storage = ServiceLocator.get_service(StorageHandler)
    print(f"Service Locator resolved: {type(resolved_storage).__name__}")


def demonstrate_refactored_components():
    """Demonstrate Refactored Components usage."""
    print("\n=== Refactored Components Demo ===")
    
    # Individual components
    model_manager = ModelManager(cache_size_limit=2)
    audio_processor = AudioProcessor(chunk_duration=30.0)
    memory_manager = MemoryManager(enable_memory_pool=True)
    
    print(f"Created components:")
    print(f"  Model Manager: {type(model_manager).__name__}")
    print(f"  Audio Processor: {type(audio_processor).__name__}")
    print(f"  Memory Manager: {type(memory_manager).__name__}")
    
    # Integrated transcriber
    transcriber = RefactoredWhisperTranscriber(
        model_name='openai/whisper-large-v3'
    )
    print(f"Created refactored transcriber: {type(transcriber).__name__}")


def demonstrate_utility_classes():
    """Demonstrate Utility Classes usage."""
    print("\n=== Utility Classes Demo ===")
    
    # Timestamp utilities
    sample_time = 3725.5  # 1 hour, 2 minutes, 5.5 seconds
    formatted_time = TimestampUtils.format_elapsed_time(sample_time)
    formatted_ms = TimestampUtils.format_elapsed_time_with_ms(sample_time)
    duration_str = TimestampUtils.seconds_to_duration_string(sample_time)
    
    print(f"Time formatting:")
    print(f"  Elapsed: {formatted_time}")
    print(f"  With MS: {formatted_ms}")
    print(f"  Duration: {duration_str}")
    
    # File validation (demo with non-existent file)
    validation_result = FileValidator.validate_any_file("/demo/path/sample.wav")
    print(f"File validation result: {validation_result.is_valid}")
    
    # Performance timing
    with PerformanceTimer("Demo Operation") as timer:
        import time
        time.sleep(0.1)  # Simulate work
    print(f"Performance timing: {timer.get_duration():.3f} seconds")


def complete_integration_demo():
    """Complete demo showing all patterns working together."""
    print("\n" + "="*50)
    print("COMPLETE INTEGRATION DEMONSTRATION")
    print("="*50)
    
    try:
        # Create the service
        service = TranscriptionService()
        
        # Note: This would work with a real audio file
        print("TranscriptionService created successfully!")
        print("Ready to process audio files using all OOP patterns:")
        print("✓ Abstract Factory Pattern")
        print("✓ Strategy Pattern") 
        print("✓ Command Pattern")
        print("✓ Observer Pattern")
        print("✓ Dependency Injection")
        print("✓ Refactored Components")
        print("✓ Utility Classes")
        
        # Show how to use it (without actual execution)
        print("\nUsage example:")
        print("results = service.transcribe_with_all_patterns(")
        print("    audio_path='path/to/audio.wav',")
        print("    language='ja',")
        print("    enable_diarization=True,")
        print("    quality='high_quality'")
        print(")")
        
    except Exception as e:
        print(f"Demo error (expected without real dependencies): {e}")


def main():
    """Main demo function showing all pattern implementations."""
    print("OOP Design Patterns Integration Demo")
    print("transcribe_audio codebase optimization")
    
    # Individual pattern demonstrations
    demonstrate_factory_pattern()
    demonstrate_strategy_pattern()
    demonstrate_command_pattern()
    demonstrate_observer_pattern()
    demonstrate_dependency_injection()
    demonstrate_refactored_components()
    demonstrate_utility_classes()
    
    # Complete integration
    complete_integration_demo()


if __name__ == "__main__":
    main()