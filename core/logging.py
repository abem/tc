"""
Unified logging configuration for the entire transcription system.
Standardizes logging setup across all modules.
"""

import logging
import logging.handlers
import sys
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime


class UnifiedLogger:
    """Centralized logger factory and configuration manager."""
    
    _loggers: Dict[str, logging.Logger] = {}
    _configured = False
    _log_level = logging.INFO
    _log_file: Optional[str] = None
    
    @classmethod
    def configure(cls, 
                  log_level: str = "INFO",
                  log_file: Optional[str] = None,
                  enable_console: bool = True,
                  enable_file: bool = True,
                  log_format: Optional[str] = None) -> None:
        """Configure the unified logging system."""
        
        cls._log_level = getattr(logging, log_level.upper())
        cls._log_file = log_file
        
        # Default format
        if log_format is None:
            log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        
        formatter = logging.Formatter(log_format)
        
        # Configure root logger
        root_logger = logging.getLogger()
        root_logger.setLevel(cls._log_level)
        
        # Clear existing handlers
        root_logger.handlers.clear()
        
        # Console handler
        if enable_console:
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setLevel(cls._log_level)
            console_handler.setFormatter(formatter)
            root_logger.addHandler(console_handler)
        
        # File handler
        if enable_file and log_file:
            log_path = Path(log_file)
            log_path.parent.mkdir(parents=True, exist_ok=True)
            
            file_handler = logging.handlers.RotatingFileHandler(
                log_file, maxBytes=10*1024*1024, backupCount=5
            )
            file_handler.setLevel(cls._log_level)
            file_handler.setFormatter(formatter)
            root_logger.addHandler(file_handler)
        
        cls._configured = True
    
    @classmethod
    def get_logger(cls, name: str) -> logging.Logger:
        """Get or create a logger for the specified module."""
        
        if not cls._configured:
            # Auto-configure with defaults if not explicitly configured
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            log_file = f"logs/transcription_{timestamp}.log"
            cls.configure(log_file=log_file)
        
        if name not in cls._loggers:
            logger = logging.getLogger(name)
            logger.setLevel(cls._log_level)
            cls._loggers[name] = logger
        
        return cls._loggers[name]


# Convenience functions for backward compatibility
def get_logger(name: str) -> logging.Logger:
    """Get a logger instance (backward compatible interface)."""
    return UnifiedLogger.get_logger(name)


class Logger:
    """Legacy Logger class for backward compatibility."""
    
    @staticmethod
    def get_logger(name: str) -> logging.Logger:
        """Get a logger instance (legacy interface)."""
        return UnifiedLogger.get_logger(name)


# Performance monitoring logger
class PerformanceLogger:
    """Specialized logger for performance metrics."""
    
    def __init__(self, name: str):
        self.logger = UnifiedLogger.get_logger(f"perf.{name}")
        self._start_time = None
    
    def start_timing(self, operation: str) -> None:
        """Start timing an operation."""
        import time
        self._start_time = time.time()
        self.logger.info(f"Started: {operation}")
    
    def end_timing(self, operation: str) -> float:
        """End timing and log duration."""
        if self._start_time is None:
            self.logger.warning(f"No start time recorded for: {operation}")
            return 0.0
        
        import time
        duration = time.time() - self._start_time
        self.logger.info(f"Completed: {operation} in {duration:.3f}s")
        self._start_time = None
        return duration
    
    def log_metric(self, metric_name: str, value: Any, unit: str = "") -> None:
        """Log a performance metric."""
        self.logger.info(f"Metric: {metric_name} = {value} {unit}".strip())
    
    def log_memory_usage(self) -> None:
        """Log current memory usage."""
        try:
            import psutil
            process = psutil.Process()
            memory_mb = process.memory_info().rss / 1024 / 1024
            self.log_metric("memory_usage", f"{memory_mb:.2f}", "MB")
        except ImportError:
            self.logger.debug("psutil not available for memory monitoring")


# Initialize default configuration if running as main module
if __name__ == "__main__":
    UnifiedLogger.configure(
        log_level="INFO",
        log_file="logs/transcription_test.log",
        enable_console=True,
        enable_file=True
    )
    
    # Test the logger
    test_logger = UnifiedLogger.get_logger("test")
    test_logger.info("Unified logging system initialized successfully")
    
    # Test performance logger
    perf_logger = PerformanceLogger("test")
    perf_logger.start_timing("test_operation")
    import time
    time.sleep(0.1)
    perf_logger.end_timing("test_operation")
    perf_logger.log_memory_usage()