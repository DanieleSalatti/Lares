"""Base classes and errors for Lares tools."""

from dataclasses import dataclass
from typing import Any


class ToolError(Exception):
    """Base exception for tool errors."""

    pass


class CommandNotAllowedError(ToolError):
    """Raised when a command is not in the allowlist."""

    def __init__(self, command: str):
        self.command = command
        super().__init__(f"Command not allowed: {command}")


class PathNotAllowedError(ToolError):
    """Raised when a path is outside allowed directories."""

    def __init__(self, path: str):
        self.path = path
        super().__init__(f"Path not allowed: {path}")


class FileBlockedError(ToolError):
    """Raised when trying to access a blocked file."""

    def __init__(self, path: str):
        self.path = path
        super().__init__(f"File is blocked (may contain secrets): {path}")


class InvalidToolCodeError(ToolError):
    """Raised when tool code is invalid."""

    def __init__(self, message: str):
        super().__init__(f"Invalid tool code: {message}")


@dataclass
class ToolResult:
    """Result from a tool execution."""

    success: bool
    message: str
    data: dict[str, Any] | None = None

    def __str__(self) -> str:
        return self.message
