"""Tests for error handling utilities."""

from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest

from lares.error_handling import (
    GracefulShutdown,
    RetryError,
    discord_error_handler,
    retry_async,
    safe_string_truncate,
)


class TestRetryAsync:
    """Tests for retry_async function."""

    @pytest.mark.asyncio
    async def test_succeeds_first_try(self):
        """Function succeeds on first attempt."""
        mock_func = AsyncMock(return_value="success")
        result = await retry_async(mock_func, max_attempts=3)
        assert result == "success"
        assert mock_func.call_count == 1

    @pytest.mark.asyncio
    async def test_retries_on_failure(self):
        """Function retries on failure and eventually succeeds."""
        mock_func = AsyncMock(side_effect=[ValueError, ValueError, "success"])
        result = await retry_async(
            mock_func,
            max_attempts=3,
            delay=0.01,  # Short delay for tests
            exceptions=(ValueError,),
        )
        assert result == "success"
        assert mock_func.call_count == 3

    @pytest.mark.asyncio
    async def test_raises_retry_error_when_exhausted(self):
        """Raises RetryError when all attempts fail."""
        mock_func = AsyncMock(side_effect=ValueError("always fails"))
        with pytest.raises(RetryError):
            await retry_async(
                mock_func,
                max_attempts=2,
                delay=0.01,
                exceptions=(ValueError,),
            )
        assert mock_func.call_count == 2

    @pytest.mark.asyncio
    async def test_only_catches_specified_exceptions(self):
        """Only catches exceptions in the exceptions tuple."""
        mock_func = AsyncMock(side_effect=TypeError("not caught"))
        with pytest.raises(TypeError):
            await retry_async(
                mock_func,
                max_attempts=3,
                exceptions=(ValueError,),  # TypeError not in list
            )
        # Should fail immediately without retrying
        assert mock_func.call_count == 1

    @pytest.mark.asyncio
    async def test_backoff_factor_increases_delay(self):
        """Delay increases with backoff factor."""
        delays = []

        async def mock_sleep(seconds):
            delays.append(seconds)

        mock_func = AsyncMock(side_effect=[ValueError, ValueError, "success"])

        with patch("asyncio.sleep", mock_sleep):
            await retry_async(
                mock_func,
                max_attempts=3,
                delay=1.0,
                backoff_factor=2.0,
                exceptions=(ValueError,),
            )

        # First retry: 1.0s, second retry: 2.0s (1.0 * 2.0)
        assert delays == [1.0, 2.0]


class TestDiscordErrorHandler:
    """Tests for discord_error_handler decorator."""

    def test_decorator_returns_callable(self):
        """Decorator returns a callable."""
        @discord_error_handler("test_operation")
        async def sample_func():
            return "ok"

        assert callable(sample_func)

    @pytest.mark.asyncio
    async def test_successful_execution(self):
        """Decorated function executes normally on success."""
        @discord_error_handler("test_operation")
        async def sample_func():
            return "result"

        result = await sample_func()
        assert result == "result"

    @pytest.mark.asyncio
    async def test_catches_discord_forbidden(self):
        """Catches discord.Forbidden and logs."""
        mock_response = MagicMock()
        mock_response.status = 403

        @discord_error_handler("test_operation")
        async def sample_func():
            raise discord.Forbidden(mock_response, "No permission")

        # Should not raise, returns None
        result = await sample_func()
        assert result is None

    @pytest.mark.asyncio
    async def test_catches_discord_not_found(self):
        """Catches discord.NotFound and logs."""
        mock_response = MagicMock()
        mock_response.status = 404

        @discord_error_handler("test_operation")
        async def sample_func():
            raise discord.NotFound(mock_response, "Not found")

        result = await sample_func()
        assert result is None


class TestGracefulShutdown:
    """Tests for GracefulShutdown context manager."""

    @pytest.mark.asyncio
    async def test_context_manager_normal_exit(self):
        """Context manager allows normal exit."""
        shutdown = GracefulShutdown("test_operation")
        async with shutdown:
            pass  # Normal execution
        # Should complete without error

    @pytest.mark.asyncio
    async def test_context_manager_with_exception(self):
        """Context manager handles exceptions gracefully."""
        shutdown = GracefulShutdown("test_operation")
        with pytest.raises(ValueError):
            async with shutdown:
                raise ValueError("test error")
        # Exception should propagate

    def test_init_stores_operation_name(self):
        """Constructor stores operation name."""
        shutdown = GracefulShutdown("my_operation")
        assert shutdown.operation_name == "my_operation"


class TestSafeStringTruncate:
    """Tests for safe_string_truncate function."""

    def test_short_string_unchanged(self):
        """Short strings are not truncated."""
        result = safe_string_truncate("hello", max_length=100)
        assert result == "hello"

    def test_long_string_truncated(self):
        """Long strings are truncated with ellipsis."""
        result = safe_string_truncate("a" * 200, max_length=100)
        assert len(result) <= 100
        assert result.endswith("...")

    def test_exact_length_unchanged(self):
        """String at exact max length is not truncated."""
        text = "a" * 100
        result = safe_string_truncate(text, max_length=100)
        assert result == text

    def test_empty_string(self):
        """Empty string returns empty string."""
        result = safe_string_truncate("", max_length=100)
        assert result == ""

    def test_custom_max_length(self):
        """Custom max length is respected."""
        result = safe_string_truncate("hello world", max_length=5)
        assert len(result) <= 5


class TestRetryError:
    """Tests for RetryError exception."""

    def test_retry_error_is_exception(self):
        """RetryError is an Exception subclass."""
        error = RetryError("test message")
        assert isinstance(error, Exception)
        assert str(error) == "test message"
