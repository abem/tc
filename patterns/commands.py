"""
Command Pattern implementation for decoupling CLI operations and business logic.
Provides testable, composable, and reusable command objects for audio processing operations.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Callable, Union
from pathlib import Path
import logging
from datetime import datetime

from patterns.factories import ModelFactoryRegistry, ProcessingConfiguration
from patterns.strategies import StrategyRegistry, create_device_info, create_audio_info


@dataclass
class CommandResult:
    """Result object for command execution."""
    success: bool
    data: Any = None
    error: Optional[Exception] = None
    message: str = ""
    execution_time: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AudioProcessingContext:
    """Context object containing all necessary information for audio processing."""
    input_path: str
    output_path: Optional[str] = None
    language: str = 'ja'
    enable_diarization: bool = False
    config: Optional[ProcessingConfiguration] = None
    upload_to_gdrive: bool = True
    timestamp_format: str = 'elapsed'
    quality_preference: str = 'balanced'


class Command(ABC):
    """Abstract base class for all commands."""
    
    def __init__(self, context: Optional[Dict[str, Any]] = None):
        self.context = context or {}
        self.logger = logging.getLogger(self.__class__.__name__)
        self._start_time = None
        self._end_time = None
    
    @abstractmethod
    def execute(self) -> CommandResult:
        """Execute the command and return result."""
        pass
    
    def can_execute(self) -> bool:
        """Check if command can be executed with current context."""
        return True
    
    def validate_context(self) -> bool:
        """Validate command context."""
        return True
    
    def _start_timing(self):
        """Start execution timing."""
        self._start_time = datetime.now()
    
    def _end_timing(self) -> float:
        """End timing and return execution time in seconds."""
        self._end_time = datetime.now()
        if self._start_time:
            return (self._end_time - self._start_time).total_seconds()
        return 0.0
    
    def _create_result(
        self,
        success: bool,
        data: Any = None,
        error: Optional[Exception] = None,
        message: str = ""
    ) -> CommandResult:
        """Create command result with timing information."""
        return CommandResult(
            success=success,
            data=data,
            error=error,
            message=message,
            execution_time=self._end_timing(),
            metadata={'command_class': self.__class__.__name__}
        )


class ValidateInputCommand(Command):
    """Command to validate input audio file."""
    
    def __init__(self, audio_path: str, **kwargs):
        super().__init__(kwargs)
        self.audio_path = Path(audio_path)
    
    def execute(self) -> CommandResult:
        """Validate input audio file exists and is accessible."""
        self._start_timing()
        
        try:
            if not self.audio_path.exists():
                return self._create_result(
                    False,
                    error=FileNotFoundError(f"音声ファイルが見つかりません: {self.audio_path}"),
                    message="Input file not found"
                )
            
            if not self.audio_path.is_file():
                return self._create_result(
                    False,
                    error=ValueError(f"指定されたパスはファイルではありません: {self.audio_path}"),
                    message="Path is not a file"
                )
            
            # Check if file is readable
            try:
                with open(self.audio_path, 'rb') as f:
                    f.read(1024)  # Read first 1KB to check accessibility
            except PermissionError:
                return self._create_result(
                    False,
                    error=PermissionError(f"ファイルへの読み取り権限がありません: {self.audio_path}"),
                    message="Permission denied"
                )
            
            file_size = self.audio_path.stat().st_size
            return self._create_result(
                True,
                data={'file_path': str(self.audio_path), 'file_size': file_size},
                message=f"Input validation successful: {self.audio_path.name}"
            )
            
        except Exception as e:
            return self._create_result(
                False,
                error=e,
                message=f"Validation failed: {str(e)}"
            )


class LoadConfigurationCommand(Command):
    """Command to load and validate configuration."""
    
    def __init__(self, context: AudioProcessingContext, **kwargs):
        super().__init__(kwargs)
        self.processing_context = context
    
    def execute(self) -> CommandResult:
        """Load processing configuration."""
        self._start_timing()
        
        try:
            if self.processing_context.config is None:
                # Create configuration from context
                config = ProcessingConfiguration.create_for_language(
                    language=self.processing_context.language,
                    enable_diarization=self.processing_context.enable_diarization
                )
                self.processing_context.config = config
            
            return self._create_result(
                True,
                data=self.processing_context.config,
                message="Configuration loaded successfully"
            )
            
        except Exception as e:
            return self._create_result(
                False,
                error=e,
                message=f"Configuration loading failed: {str(e)}"
            )


class LoadModelsCommand(Command):
    """Command to load transcription and diarization models."""
    
    def __init__(self, config: ProcessingConfiguration, **kwargs):
        super().__init__(kwargs)
        self.config = config
        self.transcriber = None
        self.diarizer = None
    
    def execute(self) -> CommandResult:
        """Load required models based on configuration."""
        self._start_timing()
        
        try:
            factory = ModelFactoryRegistry.get_factory('whisper')
            
            # Load transcriber
            self.transcriber = factory.create_transcriber(self.config.transcription)
            self.transcriber.load_model()
            
            # Load diarizer if needed
            if self.config.enable_speaker_diarization and self.config.diarization:
                self.diarizer = factory.create_diarizer(self.config.diarization)
            
            return self._create_result(
                True,
                data={
                    'transcriber': self.transcriber,
                    'diarizer': self.diarizer
                },
                message="Models loaded successfully"
            )
            
        except Exception as e:
            return self._create_result(
                False,
                error=e,
                message=f"Model loading failed: {str(e)}"
            )


class TranscribeAudioCommand(Command):
    """Command to transcribe audio file."""
    
    def __init__(
        self,
        audio_path: str,
        transcriber: Any,
        timestamp_strategy_name: str = 'elapsed',
        **kwargs
    ):
        super().__init__(kwargs)
        self.audio_path = audio_path
        self.transcriber = transcriber
        self.timestamp_strategy = StrategyRegistry.get_timestamp_strategy(timestamp_strategy_name)
    
    def execute(self) -> CommandResult:
        """Execute transcription."""
        self._start_timing()
        
        try:
            # Perform transcription
            transcription_result = self.transcriber.transcribe(self.audio_path)
            
            # Format with timestamp strategy
            if hasattr(self.transcriber, 'format_with_strategy'):
                formatted_result = self.transcriber.format_with_strategy(
                    transcription_result,
                    self.timestamp_strategy
                )
            else:
                formatted_result = transcription_result
            
            return self._create_result(
                True,
                data=formatted_result,
                message="Transcription completed successfully"
            )
            
        except Exception as e:
            return self._create_result(
                False,
                error=e,
                message=f"Transcription failed: {str(e)}"
            )


class PerformDiarizationCommand(Command):
    """Command to perform speaker diarization."""
    
    def __init__(self, audio_path: str, diarizer: Any, **kwargs):
        super().__init__(kwargs)
        self.audio_path = audio_path
        self.diarizer = diarizer
    
    def execute(self) -> CommandResult:
        """Execute speaker diarization."""
        self._start_timing()
        
        try:
            diarization_result = self.diarizer.diarize(self.audio_path)
            
            return self._create_result(
                True,
                data=diarization_result,
                message="Speaker diarization completed successfully"
            )
            
        except Exception as e:
            return self._create_result(
                False,
                error=e,
                message=f"Speaker diarization failed: {str(e)}"
            )


class CombineTranscriptionDiarizationCommand(Command):
    """Command to combine transcription and diarization results."""
    
    def __init__(
        self,
        transcription_result: Any,
        diarization_result: Any,
        **kwargs
    ):
        super().__init__(kwargs)
        self.transcription_result = transcription_result
        self.diarization_result = diarization_result
    
    def execute(self) -> CommandResult:
        """Combine transcription and diarization results."""
        self._start_timing()
        
        try:
            # Implementation would combine the results
            # This is a placeholder for the actual combination logic
            combined_result = {
                'transcription': self.transcription_result,
                'diarization': self.diarization_result,
                'combined_text': self._combine_results()
            }
            
            return self._create_result(
                True,
                data=combined_result,
                message="Results combined successfully"
            )
            
        except Exception as e:
            return self._create_result(
                False,
                error=e,
                message=f"Result combination failed: {str(e)}"
            )
    
    def _combine_results(self) -> str:
        """Combine transcription and diarization into formatted text."""
        # Placeholder for actual implementation
        return str(self.transcription_result)


class SaveResultsCommand(Command):
    """Command to save results to file."""
    
    def __init__(
        self,
        results: Any,
        output_path: str,
        format_type: str = 'txt',
        **kwargs
    ):
        super().__init__(kwargs)
        self.results = results
        self.output_path = Path(output_path)
        self.format_type = format_type
    
    def execute(self) -> CommandResult:
        """Save results to specified file."""
        self._start_timing()
        
        try:
            # Ensure output directory exists
            self.output_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Save based on format type
            if self.format_type == 'txt':
                self._save_as_text()
            elif self.format_type == 'json':
                self._save_as_json()
            else:
                raise ValueError(f"Unsupported format type: {self.format_type}")
            
            return self._create_result(
                True,
                data={'output_path': str(self.output_path)},
                message=f"Results saved to {self.output_path}"
            )
            
        except Exception as e:
            return self._create_result(
                False,
                error=e,
                message=f"Save failed: {str(e)}"
            )
    
    def _save_as_text(self):
        """Save results as plain text."""
        with open(self.output_path, 'w', encoding='utf-8') as f:
            if isinstance(self.results, dict) and 'combined_text' in self.results:
                f.write(self.results['combined_text'])
            else:
                f.write(str(self.results))
    
    def _save_as_json(self):
        """Save results as JSON."""
        import json
        with open(self.output_path, 'w', encoding='utf-8') as f:
            json.dump(self.results, f, ensure_ascii=False, indent=2)


class UploadToGDriveCommand(Command):
    """Command to upload results to Google Drive."""
    
    def __init__(self, file_path: str, **kwargs):
        super().__init__(kwargs)
        self.file_path = Path(file_path)
    
    def execute(self) -> CommandResult:
        """Upload file to Google Drive."""
        self._start_timing()
        
        try:
            from gdrive_handler import GDriveHandler
            
            gdrive = GDriveHandler()
            upload_result = gdrive.upload_file(str(self.file_path))
            
            return self._create_result(
                True,
                data=upload_result,
                message="File uploaded to Google Drive successfully"
            )
            
        except Exception as e:
            return self._create_result(
                False,
                error=e,
                message=f"Google Drive upload failed: {str(e)}"
            )


class CompositeCommand(Command):
    """Composite command that executes multiple commands in sequence."""
    
    def __init__(self, commands: List[Command], **kwargs):
        super().__init__(kwargs)
        self.commands = commands
        self.results: List[CommandResult] = []
    
    def execute(self) -> CommandResult:
        """Execute all commands in sequence."""
        self._start_timing()
        
        all_success = True
        combined_data = {}
        error_messages = []
        
        for i, command in enumerate(self.commands):
            try:
                result = command.execute()
                self.results.append(result)
                
                if not result.success:
                    all_success = False
                    error_messages.append(f"Command {i+1}: {result.message}")
                else:
                    if result.data:
                        combined_data[f"command_{i+1}"] = result.data
                        
            except Exception as e:
                all_success = False
                error_result = CommandResult(
                    success=False,
                    error=e,
                    message=f"Command {i+1} execution failed: {str(e)}"
                )
                self.results.append(error_result)
                error_messages.append(error_result.message)
        
        if all_success:
            message = f"All {len(self.commands)} commands executed successfully"
        else:
            message = f"Command execution completed with errors: {'; '.join(error_messages)}"
        
        return self._create_result(
            all_success,
            data=combined_data,
            message=message
        )


class AudioProcessingPipeline(CompositeCommand):
    """Complete audio processing pipeline as a composite command."""
    
    @classmethod
    def create_full_pipeline(
        cls,
        context: AudioProcessingContext
    ) -> 'AudioProcessingPipeline':
        """Create complete audio processing pipeline."""
        
        commands = [
            # 1. Validate input
            ValidateInputCommand(context.input_path),
            
            # 2. Load configuration
            LoadConfigurationCommand(context),
            
            # 3. Load models (will be updated after config is loaded)
            LoadModelsCommand(context.config) if context.config else None,
        ]
        
        # Filter out None commands
        commands = [cmd for cmd in commands if cmd is not None]
        
        return cls(commands)
    
    def execute(self) -> CommandResult:
        """Execute full pipeline with dynamic command creation."""
        # First execute basic setup commands
        basic_result = super().execute()
        
        if not basic_result.success:
            return basic_result
        
        # Extract loaded models and continue pipeline
        try:
            models_data = basic_result.data.get('command_3', {})
            transcriber = models_data.get('transcriber')
            diarizer = models_data.get('diarizer')
            
            # Continue with processing commands
            processing_commands = []
            
            if transcriber:
                processing_commands.append(
                    TranscribeAudioCommand(
                        audio_path=self.context.get('input_path'),
                        transcriber=transcriber,
                        timestamp_strategy_name=self.context.get('timestamp_format', 'elapsed')
                    )
                )
            
            if diarizer:
                processing_commands.append(
                    PerformDiarizationCommand(
                        audio_path=self.context.get('input_path'),
                        diarizer=diarizer
                    )
                )
            
            # Execute processing commands
            processing_pipeline = CompositeCommand(processing_commands)
            processing_result = processing_pipeline.execute()
            
            # Combine results
            combined_data = {**basic_result.data}
            if processing_result.data:
                combined_data.update(processing_result.data)
            
            return CommandResult(
                success=basic_result.success and processing_result.success,
                data=combined_data,
                message="Full pipeline execution completed",
                execution_time=basic_result.execution_time + processing_result.execution_time
            )
            
        except Exception as e:
            return self._create_result(
                False,
                error=e,
                message=f"Pipeline execution failed: {str(e)}"
            )


class CommandInvoker:
    """Invoker class for executing commands with logging and error handling."""
    
    def __init__(self):
        self.logger = logging.getLogger(self.__class__.__name__)
        self.command_history: List[tuple[Command, CommandResult]] = []
    
    def execute_command(self, command: Command) -> CommandResult:
        """Execute a single command with logging."""
        self.logger.info(f"Executing command: {command.__class__.__name__}")
        
        if not command.can_execute():
            result = CommandResult(
                success=False,
                message=f"Command {command.__class__.__name__} cannot be executed"
            )
            self.command_history.append((command, result))
            return result
        
        try:
            result = command.execute()
            self.command_history.append((command, result))
            
            if result.success:
                self.logger.info(f"Command completed successfully: {result.message}")
            else:
                self.logger.error(f"Command failed: {result.message}")
                if result.error:
                    self.logger.exception("Command error details", exc_info=result.error)
            
            return result
            
        except Exception as e:
            self.logger.exception(f"Unexpected error during command execution: {str(e)}")
            result = CommandResult(
                success=False,
                error=e,
                message=f"Unexpected error: {str(e)}"
            )
            self.command_history.append((command, result))
            return result
    
    def execute_pipeline(self, context: AudioProcessingContext) -> CommandResult:
        """Execute complete audio processing pipeline."""
        pipeline = AudioProcessingPipeline.create_full_pipeline(context)
        return self.execute_command(pipeline)
    
    def get_command_history(self) -> List[tuple[Command, CommandResult]]:
        """Get command execution history."""
        return self.command_history.copy()
    
    def clear_history(self):
        """Clear command execution history."""
        self.command_history.clear()