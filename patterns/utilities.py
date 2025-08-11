"""
Utility classes to eliminate code duplication across the transcribe_audio codebase.
Provides common functionality for timestamp formatting, file validation, error handling, and more.
"""

import os
import time
import hashlib
import tempfile
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple, Union, Callable
from pathlib import Path
from contextlib import contextmanager
import threading


@dataclass
class FileValidationResult:
    """Result of file validation."""
    is_valid: bool
    file_path: Path
    file_size: int
    error_message: Optional[str] = None
    metadata: Dict[str, Any] = None


class TimestampUtils:
    """Utility class for timestamp formatting operations."""
    
    @staticmethod
    def format_elapsed_time(seconds: float) -> str:
        """Format seconds as elapsed time (HH:MM:SS)."""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        return f"[{hours:02d}:{minutes:02d}:{secs:02d}]"
    
    @staticmethod
    def format_elapsed_time_with_ms(seconds: float) -> str:
        """Format seconds as elapsed time with milliseconds (HH:MM:SS.mmm)."""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        milliseconds = int((seconds % 1) * 1000)
        return f"[{hours:02d}:{minutes:02d}:{secs:02d}.{milliseconds:03d}]"
    
    @staticmethod
    def format_absolute_time(seconds: float, start_timestamp: float) -> str:
        """Format as absolute timestamp from start time."""
        absolute_time = start_timestamp + seconds
        hours = int(absolute_time // 3600) % 24
        minutes = int((absolute_time % 3600) // 60)
        secs = int(absolute_time % 60)
        return f"[{hours:02d}:{minutes:02d}:{secs:02d}]"
    
    @staticmethod
    def format_relative_time(seconds: float, reference_time: float) -> str:
        """Format as relative time from reference point."""
        relative_seconds = seconds - reference_time
        sign = "+" if relative_seconds >= 0 else "-"
        relative_seconds = abs(relative_seconds)
        
        hours = int(relative_seconds // 3600)
        minutes = int((relative_seconds % 3600) // 60)
        secs = int(relative_seconds % 60)
        return f"[{sign}{hours:02d}:{minutes:02d}:{secs:02d}]"
    
    @staticmethod
    def seconds_to_duration_string(seconds: float) -> str:
        """Convert seconds to human-readable duration string."""
        if seconds < 60:
            return f"{seconds:.1f} seconds"
        elif seconds < 3600:
            minutes = seconds / 60
            return f"{minutes:.1f} minutes"
        else:
            hours = seconds / 3600
            return f"{hours:.1f} hours"
    
    @staticmethod
    def parse_timestamp_string(timestamp_str: str) -> Optional[float]:
        """Parse timestamp string back to seconds."""
        try:
            # Remove brackets if present
            timestamp_str = timestamp_str.strip('[]')
            
            # Handle different formats
            if '.' in timestamp_str:
                # Format with milliseconds
                time_part, ms_part = timestamp_str.split('.')
                ms = int(ms_part[:3])  # Take first 3 digits
            else:
                time_part = timestamp_str
                ms = 0
            
            # Parse HH:MM:SS
            parts = time_part.split(':')
            if len(parts) == 3:
                hours, minutes, seconds = map(int, parts)
                total_seconds = hours * 3600 + minutes * 60 + seconds + ms / 1000.0
                return total_seconds
            
            return None
            
        except (ValueError, IndexError):
            return None


class FileValidator:
    """Utility class for file validation operations."""
    
    AUDIO_EXTENSIONS = {'.wav', '.mp3', '.m4a', '.flac', '.ogg', '.wma', '.aac', '.mp4'}
    TEXT_EXTENSIONS = {'.txt', '.md', '.json', '.yaml', '.yml'}
    
    @classmethod
    def validate_audio_file(cls, file_path: Union[str, Path]) -> FileValidationResult:
        """Validate audio file exists and is accessible."""
        return cls._validate_file(file_path, cls.AUDIO_EXTENSIONS, "audio")
    
    @classmethod
    def validate_text_file(cls, file_path: Union[str, Path]) -> FileValidationResult:
        """Validate text file exists and is accessible."""
        return cls._validate_file(file_path, cls.TEXT_EXTENSIONS, "text")
    
    @classmethod
    def validate_any_file(cls, file_path: Union[str, Path]) -> FileValidationResult:
        """Validate any file exists and is accessible."""
        return cls._validate_file(file_path, None, "file")
    
    @classmethod
    def _validate_file(
        cls,
        file_path: Union[str, Path],
        allowed_extensions: Optional[set],
        file_type: str
    ) -> FileValidationResult:
        """Internal file validation logic."""
        try:
            path = Path(file_path)
            
            # Check existence
            if not path.exists():
                return FileValidationResult(
                    is_valid=False,
                    file_path=path,
                    file_size=0,
                    error_message=f"{file_type.title()} file not found: {path}"
                )
            
            # Check if it's a file
            if not path.is_file():
                return FileValidationResult(
                    is_valid=False,
                    file_path=path,
                    file_size=0,
                    error_message=f"Path is not a file: {path}"
                )
            
            # Check extension
            if allowed_extensions and path.suffix.lower() not in allowed_extensions:
                return FileValidationResult(
                    is_valid=False,
                    file_path=path,
                    file_size=0,
                    error_message=f"Unsupported {file_type} format: {path.suffix}"
                )
            
            # Check readability
            try:
                with open(path, 'rb') as f:
                    f.read(1024)  # Try to read first 1KB
            except PermissionError:
                return FileValidationResult(
                    is_valid=False,
                    file_path=path,
                    file_size=0,
                    error_message=f"Permission denied: {path}"
                )
            
            # Get file info
            file_size = path.stat().st_size
            metadata = {
                'extension': path.suffix.lower(),
                'name': path.name,
                'parent': str(path.parent),
                'modified_time': path.stat().st_mtime
            }
            
            return FileValidationResult(
                is_valid=True,
                file_path=path,
                file_size=file_size,
                metadata=metadata
            )
            
        except Exception as e:
            return FileValidationResult(
                is_valid=False,
                file_path=Path(file_path),
                file_size=0,
                error_message=f"Validation error: {str(e)}"
            )
    
    @classmethod
    def get_file_hash(cls, file_path: Union[str, Path], algorithm: str = 'sha256') -> Optional[str]:
        """Calculate hash of file contents."""
        try:
            hash_func = getattr(hashlib, algorithm.lower())()
            
            with open(file_path, 'rb') as f:
                for chunk in iter(lambda: f.read(8192), b""):
                    hash_func.update(chunk)
            
            return hash_func.hexdigest()
            
        except Exception:
            return None


class PathUtils:
    """Utility class for path operations."""
    
    @staticmethod
    def ensure_directory_exists(directory_path: Union[str, Path]) -> Path:
        """Ensure directory exists, create if necessary."""
        path = Path(directory_path)
        path.mkdir(parents=True, exist_ok=True)
        return path
    
    @staticmethod
    def get_unique_filename(base_path: Union[str, Path], suffix: str = "") -> Path:
        """Generate unique filename by adding counter if needed."""
        path = Path(base_path)
        
        if suffix and not path.name.endswith(suffix):
            path = path.with_suffix(suffix)
        
        if not path.exists():
            return path
        
        # Generate unique name
        stem = path.stem
        suffix_ext = path.suffix
        parent = path.parent
        counter = 1
        
        while True:
            new_name = f"{stem}_{counter}{suffix_ext}"
            new_path = parent / new_name
            if not new_path.exists():
                return new_path
            counter += 1
    
    @staticmethod
    def get_relative_path(target_path: Union[str, Path], base_path: Union[str, Path]) -> Path:
        """Get relative path from base to target."""
        return Path(target_path).relative_to(Path(base_path))
    
    @staticmethod
    def sanitize_filename(filename: str, replacement: str = "_") -> str:
        """Sanitize filename by replacing invalid characters."""
        invalid_chars = '<>:"/\\|?*'
        sanitized = filename
        
        for char in invalid_chars:
            sanitized = sanitized.replace(char, replacement)
        
        # Remove leading/trailing spaces and dots
        sanitized = sanitized.strip(' .')
        
        # Limit length
        if len(sanitized) > 200:
            sanitized = sanitized[:200]
        
        return sanitized


class TemporaryFileManager:
    """Context manager for temporary file operations."""
    
    def __init__(self, prefix: str = "transcribe_", suffix: str = ".tmp", directory: Optional[str] = None):
        self.prefix = prefix
        self.suffix = suffix
        self.directory = directory
        self.temp_files: List[Path] = []
        self._lock = threading.RLock()
    
    @contextmanager
    def create_temp_file(self, mode: str = 'w+b'):
        """Create temporary file with automatic cleanup."""
        temp_fd, temp_path = tempfile.mkstemp(
            prefix=self.prefix,
            suffix=self.suffix,
            dir=self.directory
        )
        
        temp_path = Path(temp_path)
        
        with self._lock:
            self.temp_files.append(temp_path)
        
        try:
            with os.fdopen(temp_fd, mode) as temp_file:
                yield temp_file, temp_path
        finally:
            self._cleanup_file(temp_path)
    
    @contextmanager
    def create_temp_directory(self):
        """Create temporary directory with automatic cleanup."""
        temp_dir = Path(tempfile.mkdtemp(prefix=self.prefix, dir=self.directory))
        
        with self._lock:
            self.temp_files.append(temp_dir)
        
        try:
            yield temp_dir
        finally:
            self._cleanup_directory(temp_dir)
    
    def _cleanup_file(self, file_path: Path):
        """Clean up single file."""
        try:
            if file_path.exists():
                file_path.unlink()
            
            with self._lock:
                if file_path in self.temp_files:
                    self.temp_files.remove(file_path)
                    
        except Exception:
            pass  # Ignore cleanup errors
    
    def _cleanup_directory(self, dir_path: Path):
        """Clean up directory and contents."""
        try:
            if dir_path.exists():
                import shutil
                shutil.rmtree(dir_path)
            
            with self._lock:
                if dir_path in self.temp_files:
                    self.temp_files.remove(dir_path)
                    
        except Exception:
            pass  # Ignore cleanup errors
    
    def cleanup_all(self):
        """Clean up all temporary files and directories."""
        with self._lock:
            for temp_path in self.temp_files.copy():
                if temp_path.is_file():
                    self._cleanup_file(temp_path)
                elif temp_path.is_dir():
                    self._cleanup_directory(temp_path)
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.cleanup_all()


class ErrorHandler:
    """Utility class for consistent error handling."""
    
    def __init__(self, logger: Optional[logging.Logger] = None):
        self.logger = logger or logging.getLogger(self.__class__.__name__)
    
    @contextmanager
    def handle_errors(
        self,
        operation_name: str,
        reraise: bool = True,
        default_return: Any = None
    ):
        """Context manager for consistent error handling."""
        try:
            yield
        except Exception as e:
            self.logger.error(f"{operation_name} failed: {str(e)}", exc_info=True)
            
            if reraise:
                raise
            else:
                return default_return
    
    def wrap_function(
        self,
        func: Callable,
        operation_name: Optional[str] = None,
        reraise: bool = True,
        default_return: Any = None
    ):
        """Wrap function with error handling."""
        operation_name = operation_name or func.__name__
        
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                self.logger.error(f"{operation_name} failed: {str(e)}", exc_info=True)
                
                if reraise:
                    raise
                else:
                    return default_return
        
        return wrapper


class PerformanceTimer:
    """Utility for measuring performance and timing operations."""
    
    def __init__(self, operation_name: str, logger: Optional[logging.Logger] = None):
        self.operation_name = operation_name
        self.logger = logger
        self.start_time: Optional[float] = None
        self.end_time: Optional[float] = None
    
    def start(self):
        """Start timing."""
        self.start_time = time.perf_counter()
        if self.logger:
            self.logger.info(f"Starting {self.operation_name}")
    
    def stop(self) -> float:
        """Stop timing and return duration."""
        self.end_time = time.perf_counter()
        duration = self.get_duration()
        
        if self.logger:
            self.logger.info(f"Completed {self.operation_name} in {duration:.2f} seconds")
        
        return duration
    
    def get_duration(self) -> float:
        """Get duration in seconds."""
        if self.start_time is None:
            return 0.0
        
        end_time = self.end_time or time.perf_counter()
        return end_time - self.start_time
    
    def __enter__(self):
        self.start()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()


class ConfigurationUtils:
    """Utility class for configuration operations."""
    
    @staticmethod
    def deep_merge_dicts(base_dict: Dict, update_dict: Dict) -> Dict:
        """Deep merge two dictionaries."""
        result = base_dict.copy()
        
        for key, value in update_dict.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = ConfigurationUtils.deep_merge_dicts(result[key], value)
            else:
                result[key] = value
        
        return result
    
    @staticmethod
    def get_nested_value(data: Dict, key_path: str, default: Any = None) -> Any:
        """Get value from nested dictionary using dot notation."""
        keys = key_path.split('.')
        current = data
        
        for key in keys:
            if isinstance(current, dict) and key in current:
                current = current[key]
            else:
                return default
        
        return current
    
    @staticmethod
    def set_nested_value(data: Dict, key_path: str, value: Any) -> None:
        """Set value in nested dictionary using dot notation."""
        keys = key_path.split('.')
        current = data
        
        for key in keys[:-1]:
            if key not in current:
                current[key] = {}
            current = current[key]
        
        current[keys[-1]] = value


class TextProcessingUtils:
    """Utility class for text processing operations."""
    
    @staticmethod
    def clean_transcription_text(text: str) -> str:
        """Clean and normalize transcription text."""
        # Remove excessive whitespace
        text = ' '.join(text.split())
        
        # Remove duplicate punctuation
        text = text.replace('..', '.')
        text = text.replace('??', '?')
        text = text.replace('!!', '!')
        
        # Ensure proper spacing after punctuation
        for punct in ['.', '?', '!', ',', ';', ':']:
            text = text.replace(f'{punct} ', f'{punct} ')
            text = text.replace(f'{punct}  ', f'{punct} ')
        
        return text.strip()
    
    @staticmethod
    def split_into_sentences(text: str, max_length: int = 200) -> List[str]:
        """Split text into sentences with maximum length."""
        sentences = []
        current_sentence = ""
        
        # Simple sentence splitting
        for char in text:
            current_sentence += char
            
            if char in '.?!' and len(current_sentence.strip()) > 10:
                sentences.append(current_sentence.strip())
                current_sentence = ""
            elif len(current_sentence) >= max_length:
                # Find last space to avoid breaking words
                last_space = current_sentence.rfind(' ')
                if last_space > len(current_sentence) // 2:
                    sentences.append(current_sentence[:last_space].strip())
                    current_sentence = current_sentence[last_space:].strip()
                else:
                    sentences.append(current_sentence.strip())
                    current_sentence = ""
        
        if current_sentence.strip():
            sentences.append(current_sentence.strip())
        
        return [s for s in sentences if s]
    
    @staticmethod
    def estimate_reading_time(text: str, words_per_minute: int = 200) -> float:
        """Estimate reading time in minutes."""
        word_count = len(text.split())
        return word_count / words_per_minute


# Convenience functions for common operations
def format_file_size(size_bytes: int) -> str:
    """Format file size in human-readable format."""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} PB"


def create_logger(name: str, level: int = logging.INFO) -> logging.Logger:
    """Create configured logger instance."""
    logger = logging.getLogger(name)
    
    if not logger.handlers:
        handler = logging.StreamHandler()
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(level)
    
    return logger


def retry_operation(
    func: Callable,
    max_attempts: int = 3,
    delay: float = 1.0,
    backoff_factor: float = 2.0,
    exceptions: Tuple[type, ...] = (Exception,)
) -> Any:
    """Retry operation with exponential backoff."""
    last_exception = None
    
    for attempt in range(max_attempts):
        try:
            return func()
        except exceptions as e:
            last_exception = e
            if attempt == max_attempts - 1:
                break
            
            time.sleep(delay)
            delay *= backoff_factor
    
    if last_exception:
        raise last_exception