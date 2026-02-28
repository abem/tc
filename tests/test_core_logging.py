"""
Tests for core.logging module.
"""

import pytest
import logging
from unittest.mock import patch, MagicMock


class TestUnifiedLogger:
    """Tests for UnifiedLogger."""

    def test_get_logger_returns_logger(self):
        """Test that get_logger returns a Logger instance."""
        from core.logging import UnifiedLogger

        logger = UnifiedLogger.get_logger("test_module")
        assert isinstance(logger, logging.Logger)

    def test_get_logger_same_name_returns_same_instance(self):
        """Test that same name returns same logger instance."""
        from core.logging import UnifiedLogger

        logger1 = UnifiedLogger.get_logger("same_module")
        logger2 = UnifiedLogger.get_logger("same_module")
        assert logger1 is logger2

    def test_get_logger_different_names(self):
        """Test that different names return different loggers."""
        from core.logging import UnifiedLogger

        logger1 = UnifiedLogger.get_logger("module_one")
        logger2 = UnifiedLogger.get_logger("module_two")
        # Both are loggers but tracked separately
        assert logger1.name == "module_one"
        assert logger2.name == "module_two"


class TestGetLogger:
    """Tests for convenience get_logger function."""

    def test_get_logger_function(self):
        """Test the convenience get_logger function."""
        from core.logging import get_logger

        logger = get_logger("test_convenience")
        assert isinstance(logger, logging.Logger)
        assert logger.name == "test_convenience"


class TestPerformanceLogger:
    """Tests for PerformanceLogger."""

    def test_log_metric(self):
        """Test logging a metric."""
        from core.logging import PerformanceLogger

        perf_logger = PerformanceLogger("test_perf")
        # Should not raise
        perf_logger.log_metric("test_metric", 100, "ms")

    def test_start_end_timing(self):
        """Test timing operations."""
        from core.logging import PerformanceLogger
        import time

        perf_logger = PerformanceLogger("test_timing")
        perf_logger.start_timing("test_operation")
        time.sleep(0.01)  # Small delay
        duration = perf_logger.end_timing("test_operation")

        assert duration > 0
        assert isinstance(duration, float)


class TestLoggerBackwardCompatibility:
    """Tests for backward compatibility."""

    def test_logger_class_exists(self):
        """Test that Logger class exists for backward compatibility."""
        from core.logging import Logger

        logger = Logger.get_logger("test_backward")
        assert isinstance(logger, logging.Logger)
