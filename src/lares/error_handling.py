"""Enhanced error handling utilities for Lares."""

import asyncio
import functools
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

import discord

from lares.logging_config import get_logger

log = get_logger("error_handling")

T = TypeVar("T")


class RetryError(Exception):
    """Raised when retry attempts are exhausted."""
    pass


async def retry_async(
    func: Callable[..., Awaitable[T]],
    max_attempts: int = 3,
    delay: float = 1.0,
    backoff_factor: float = 2.0,
    exceptions: tuple[type[Exception], ...] = (Exception,),
    context: dict[str, Any] | None = None,
) -> T:
    """
    Retry an async function with exponential backoff.

    Args:
        func: The async function to retry
        max_attempts: Maximum number of attempts
        delay: Initial delay between attempts (seconds)
        backoff_factor: Multiplier for delay on each retry
        exceptions: Tuple of exception types to catch and retry
        context: Additional context for logging

    Returns:
        The result of the successful function call

    Raises:
        RetryError: If all attempts fail
    """
    context = context or {}
    last_exception = None

    for attempt in range(1, max_attempts + 1):
        try:
            log.debug("retry_attempt",
                     attempt=attempt,
                     max_attempts=max_attempts,
                     function=func.__name__,
                     **context)
            result = await func()

            if attempt > 1:
                log.info("retry_succeeded",
                        attempt=attempt,
                        function=func.__name__,
                        **context)

            return result

        except exceptions as e:
            last_exception = e
            log.warning("retry_attempt_failed",
                       attempt=attempt,
                       max_attempts=max_attempts,
                       function=func.__name__,
                       error=str(e),
                       error_type=type(e).__name__,
                       **context)

            if attempt < max_attempts:
                sleep_time = delay * (backoff_factor ** (attempt - 1))
                log.debug("retry_delay", delay=sleep_time, next_attempt=attempt + 1)
                await asyncio.sleep(sleep_time)
            else:
                log.error("retry_exhausted",
                         function=func.__name__,
                         final_error=str(e),
                         **context)

    raise RetryError(f"All {max_attempts} attempts failed") from last_exception


def discord_error_handler(
    operation_name: str,
    fallback_reaction: str = "❌",
    notify_user: bool = True,
) -> Callable[[Callable[..., Awaitable[Any]]], Callable[..., Awaitable[Any]]]:
    """
    Decorator for Discord command/event handlers to provide consistent error handling.

    Args:
        operation_name: Human-readable name of the operation for logging
        fallback_reaction: Emoji to react with on errors
        notify_user: Whether to notify the user of the error
    """
    def decorator(func: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[Any]]:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            # Extract message/interaction context for error reporting
            message: discord.Message | None = None

            # Look for message in args (common pattern)
            for arg in args:
                if isinstance(arg, discord.Message):
                    message = arg
                    break
                elif hasattr(arg, 'message') and isinstance(arg.message, discord.Message):
                    message = arg.message
                    break

            try:
                return await func(*args, **kwargs)

            except discord.HTTPException as e:
                log.error("discord_http_error",
                         operation=operation_name,
                         status_code=e.status,
                         error=str(e),
                         message_id=message.id if message else None)

                if message and notify_user:
                    try:
                        await message.add_reaction("🔗")  # Network error
                    except Exception:
                        pass  # Best effort

            except discord.Forbidden as e:
                log.error("discord_permission_error",
                         operation=operation_name,
                         error=str(e),
                         message_id=message.id if message else None)

                if message and notify_user:
                    try:
                        await message.add_reaction("🚫")  # Permission denied
                    except Exception:
                        pass

            except discord.NotFound as e:
                log.warning("discord_not_found",
                           operation=operation_name,
                           error=str(e),
                           message_id=message.id if message else None)
                # Usually not worth notifying user about not found errors

            except Exception as e:
                log.error("unexpected_error",
                         operation=operation_name,
                         error=str(e),
                         error_type=type(e).__name__,
                         message_id=message.id if message else None)

                if message and notify_user:
                    try:
                        await message.add_reaction(fallback_reaction)
                    except Exception:
                        pass  # Best effort

        return wrapper
    return decorator


class GracefulShutdown:
    """Context manager for graceful shutdown of async operations."""

    def __init__(self, operation_name: str):
        self.operation_name = operation_name
        self.log = get_logger("graceful_shutdown")

    async def __aenter__(self) -> "GracefulShutdown":
        self.log.info("operation_starting", operation=self.operation_name)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> bool:
        if exc_type is None:
            self.log.info("operation_completed", operation=self.operation_name)
        else:
            self.log.error("operation_failed",
                          operation=self.operation_name,
                          error_type=exc_type.__name__,
                          error=str(exc_val))
        return False  # Don't suppress exceptions


def safe_string_truncate(text: str, max_length: int = 100) -> str:
    """Safely truncate a string for logging, handling None and non-string types."""
    if text is None:
        return "<None>"

    text_str = str(text)
    if len(text_str) <= max_length:
        return text_str

    return text_str[:max_length - 3] + "..."
