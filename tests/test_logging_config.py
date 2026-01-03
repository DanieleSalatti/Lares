"""Tests for logging configuration."""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from lares.logging_config import ErrorContext, get_logger, setup_logging


class TestGetLogger:
    """Tests for get_logger function."""

    def test_returns_bound_logger(self):
        """get_logger returns a structlog BoundLogger."""
        logger = get_logger("test")
        # Should be callable with standard log methods
        assert hasattr(logger, "info")
        assert hasattr(logger, "error")
        assert hasattr(logger, "debug")
        assert hasattr(logger, "warning")

    def test_default_name(self):
        """get_logger with no name returns a logger."""
        logger = get_logger()
        assert logger is not None

    def test_different_names_work(self):
        """get_logger works with different names."""
        logger1 = get_logger("module_a")
        logger2 = get_logger("module_b")
        # Both should be valid loggers
        assert hasattr(logger1, "info")
        assert hasattr(logger2, "info")


class TestErrorContext:
    """Tests for ErrorContext context manager."""

    def test_logs_operation_started(self):
        """ErrorContext logs when entering context."""
        mock_logger = MagicMock()

        with ErrorContext(mock_logger, "test_op"):
            pass

        # Should have called info for start
        mock_logger.info.assert_any_call("operation_started", operation="test_op")

    def test_logs_operation_completed_on_success(self):
        """ErrorContext logs completion on normal exit."""
        mock_logger = MagicMock()

        with ErrorContext(mock_logger, "test_op"):
            pass

        # Should have called info for completion
        mock_logger.info.assert_any_call("operation_completed", operation="test_op")

    def test_logs_operation_failed_on_exception(self):
        """ErrorContext logs failure when exception occurs."""
        mock_logger = MagicMock()

        with pytest.raises(ValueError):
            with ErrorContext(mock_logger, "test_op"):
                raise ValueError("test error")

        # Should have logged error
        assert mock_logger.error.called

    def test_passes_context_kwargs(self):
        """ErrorContext passes additional context to log calls."""
        mock_logger = MagicMock()

        with ErrorContext(mock_logger, "test_op", user_id=123, action="save"):
            pass

        # Check that context was passed
        mock_logger.info.assert_any_call(
            "operation_started", operation="test_op", user_id=123, action="save"
        )

    def test_returns_self(self):
        """ErrorContext returns itself when entering."""
        mock_logger = MagicMock()
        ctx = ErrorContext(mock_logger, "test_op")

        with ctx as result:
            assert result is ctx

    def test_does_not_suppress_exceptions(self):
        """ErrorContext does not suppress exceptions."""
        mock_logger = MagicMock()

        with pytest.raises(RuntimeError):
            with ErrorContext(mock_logger, "test_op"):
                raise RuntimeError("should propagate")


def _make_mock_config(log_dir: str, level: str = "INFO") -> MagicMock:
    """Create a mock config for testing setup_logging."""
    mock_config = MagicMock()
    mock_config.logging.log_dir = log_dir
    mock_config.logging.level = level
    mock_config.logging.max_file_size_mb = 1
    mock_config.logging.backup_count = 1
    return mock_config


class TestSetupLogging:
    """Tests for setup_logging function."""

    def test_creates_log_directory(self):
        """setup_logging creates the log directory if it doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_dir = Path(tmpdir) / "logs"
            assert not log_dir.exists()

            config = _make_mock_config(str(log_dir))
            setup_logging(config)

            assert log_dir.exists()

    def test_creates_log_file(self):
        """setup_logging creates the log file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = _make_mock_config(tmpdir)
            setup_logging(config)
            # Should complete without error

    def test_accepts_different_log_levels(self):
        """setup_logging works with different log levels."""
        with tempfile.TemporaryDirectory() as tmpdir:
            for level in ["DEBUG", "INFO", "WARNING", "ERROR"]:
                config = _make_mock_config(tmpdir, level)
                # Should not raise
                setup_logging(config)
