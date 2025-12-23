"""Filesystem tools for reading and writing files."""

import fnmatch
from pathlib import Path

import structlog

from lares.tools.base import FileBlockedError, PathNotAllowedError

log = structlog.get_logger()


def is_path_allowed(path: str, allowed_paths: list[str]) -> bool:
    """Check if a path is within allowed directories."""
    resolved = Path(path).resolve()

    for allowed in allowed_paths:
        allowed_resolved = Path(allowed).resolve()
        try:
            resolved.relative_to(allowed_resolved)
            return True
        except ValueError:
            continue

    return False


def is_file_blocked(path: str, blocked_patterns: list[str]) -> bool:
    """Check if a file matches any blocked pattern."""
    path_obj = Path(path)
    filename = path_obj.name

    for pattern in blocked_patterns:
        if fnmatch.fnmatch(filename, pattern):
            return True
        if fnmatch.fnmatch(str(path_obj), pattern):
            return True

    return False


def read_file(
    path: str,
    allowed_paths: list[str],
    blocked_files: list[str],
) -> str:
    """
    Read a file if it's in allowed paths and not blocked.

    Returns file contents as string.
    Raises PathNotAllowedError or FileBlockedError on violations.
    """
    if not is_path_allowed(path, allowed_paths):
        raise PathNotAllowedError(path)

    if is_file_blocked(path, blocked_files):
        raise FileBlockedError(path)

    log.info("reading_file", path=path)

    path_obj = Path(path)
    if not path_obj.exists():
        return f"Error: File not found: {path}"

    if not path_obj.is_file():
        return f"Error: Not a file: {path}"

    try:
        content = path_obj.read_text()
        log.info("file_read", path=path, size=len(content))
        return content
    except Exception as e:
        return f"Error reading file: {e}"


def write_file(
    path: str,
    content: str,
    allowed_paths: list[str],
    blocked_files: list[str],
) -> str:
    """
    Write content to a file if it's in allowed paths and not blocked.

    Returns success message or error.
    Raises PathNotAllowedError or FileBlockedError on violations.
    """
    if not is_path_allowed(path, allowed_paths):
        raise PathNotAllowedError(path)

    if is_file_blocked(path, blocked_files):
        raise FileBlockedError(path)

    log.info("writing_file", path=path, size=len(content))

    path_obj = Path(path)

    try:
        # Create parent directories if needed
        path_obj.parent.mkdir(parents=True, exist_ok=True)
        path_obj.write_text(content)
        log.info("file_written", path=path, size=len(content))
        return f"Successfully wrote {len(content)} bytes to {path}"
    except Exception as e:
        return f"Error writing file: {e}"
