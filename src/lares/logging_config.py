"""Logging configuration for Lares."""

import logging
import logging.handlers
import sys
from pathlib import Path
from typing import Any, Literal

import structlog
from structlog.types import FilteringBoundLogger, Processor

from lares.config import Config


def setup_logging(config: Config) -> None:
    """Configure structured logging with file rotation and console output."""

    # Create logs directory if it doesn't exist
    log_dir = Path(config.logging.log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)

    # Configure standard library logging
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, config.logging.level.upper()),
    )

    # Create rotating file handler
    log_file = log_dir / "lares.log"
    file_handler = logging.handlers.RotatingFileHandler(
        str(log_file),
        maxBytes=config.logging.max_file_size_mb * 1024 * 1024,  # Convert to bytes
        backupCount=config.logging.backup_count,
        encoding='utf-8'
    )
    file_handler.setLevel(getattr(logging, config.logging.level.upper()))

    # Add file handler to root logger
    root_logger = logging.getLogger()
    root_logger.addHandler(file_handler)

    # Configure structlog
    timestamper = structlog.processors.TimeStamper(fmt="ISO")

    processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.StackInfoRenderer(),
        timestamper,
    ]

    if config.logging.json_format:
        # JSON format for production
        processors.append(structlog.processors.JSONRenderer())
    else:
        # Human-readable format for development
        processors.extend([
            structlog.dev.ConsoleRenderer(colors=True),
        ])

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, config.logging.level.upper())
        ),
        logger_factory=structlog.WriteLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str = "") -> FilteringBoundLogger:
    """Get a structured logger instance."""
    logger: FilteringBoundLogger = structlog.get_logger(name)
    return logger


class ErrorContext:
    """Context manager for enriched error logging."""

    def __init__(self, logger: FilteringBoundLogger, operation: str, **context: Any):
        self.logger = logger
        self.operation = operation
        self.context = context

    def __enter__(self) -> "ErrorContext":
        self.logger.info("operation_started", operation=self.operation, **self.context)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> Literal[False]:
        if exc_type is None:
            self.logger.info("operation_completed", operation=self.operation, **self.context)
        else:
            self.logger.error(
                "operation_failed",
                operation=self.operation,
                error_type=exc_type.__name__,
                error_message=str(exc_val),
                **self.context
            )
        return False  # Don't suppress exceptions
