"""Shell command execution tools."""

import subprocess
from pathlib import Path

import structlog

from lares.tools.base import CommandNotAllowedError

log = structlog.get_logger()


def is_command_allowed(command: str, allowlist: list[str]) -> bool:
    """Check if a command matches any pattern in the allowlist."""
    # Extract the base command (first word)
    cmd_parts = command.strip().split()
    if not cmd_parts:
        return False

    base_cmd = cmd_parts[0]

    for pattern in allowlist:
        pattern_parts = pattern.strip().split()
        if not pattern_parts:
            continue

        pattern_base = pattern_parts[0]

        # Check if base command matches
        if base_cmd == pattern_base:
            # If pattern is just the base command, allow any args
            if len(pattern_parts) == 1:
                return True
            # If pattern has specific args, check prefix match
            if command.startswith(pattern):
                return True

    return False


def add_to_allowlist(command: str, allowlist_file: Path, allowlist: list[str]) -> None:
    """Add a command to the allowlist and persist it."""
    # Normalize: just add the base command or specific pattern
    cmd_parts = command.strip().split()
    if not cmd_parts:
        return

    # Add the base command to allow all variations
    base_cmd = cmd_parts[0]

    if base_cmd not in allowlist:
        allowlist.append(base_cmd)
        with open(allowlist_file, "a") as f:
            f.write(f"{base_cmd}\n")
        log.info("command_added_to_allowlist", command=base_cmd)


def run_command(
    command: str,
    allowlist: list[str],
    working_dir: str | None = None,
    timeout: int = 30,
) -> dict[str, str | int]:
    """
    Execute a shell command if it's in the allowlist.

    Returns dict with 'stdout', 'stderr', and 'returncode'.
    Raises CommandNotAllowedError if command is not allowed.
    """
    if not is_command_allowed(command, allowlist):
        raise CommandNotAllowedError(command)

    log.info("running_command", command=command, working_dir=working_dir)

    try:
        result = subprocess.run(
            command,
            shell=True,
            cwd=working_dir,
            capture_output=True,
            text=True,
            timeout=timeout,
        )

        log.info(
            "command_completed",
            command=command,
            returncode=result.returncode,
            stdout_len=len(result.stdout),
        )

        return {
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode,
        }

    except subprocess.TimeoutExpired:
        log.warning("command_timeout", command=command, timeout=timeout)
        return {
            "stdout": "",
            "stderr": f"Command timed out after {timeout} seconds",
            "returncode": -1,
        }
