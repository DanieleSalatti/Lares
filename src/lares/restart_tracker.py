"""Track restart state for context injection.

This module provides restart awareness so Lares knows when/why it was restarted.
"""

import json
import os
from datetime import datetime
from pathlib import Path

# Default location for state file
DEFAULT_STATE_FILE = Path(__file__).parent.parent.parent / "data" / "restart_state.json"


def get_state_file() -> Path:
    """Get the path to the restart state file."""
    return Path(os.getenv("LARES_RESTART_STATE_FILE", str(DEFAULT_STATE_FILE)))


def record_startup(reason: str = "unknown") -> dict:
    """Record a startup event and return previous state if any.

    Args:
        reason: Why the startup happened (manual, crash, self-restart, etc.)

    Returns:
        Dict with previous_startup info (or None if first run)
    """
    state_file = get_state_file()
    state_file.parent.mkdir(parents=True, exist_ok=True)

    previous_state = None
    if state_file.exists():
        try:
            with open(state_file) as f:
                previous_state = json.load(f)
        except (OSError, json.JSONDecodeError):
            previous_state = None

    current_state = {
        "startup_time": datetime.now().isoformat(),
        "startup_reason": reason,
        "previous_startup": previous_state.get("startup_time") if previous_state else None,
    }

    with open(state_file, "w") as f:
        json.dump(current_state, f, indent=2)

    return {
        "previous_startup": previous_state,
        "current_startup": current_state,
    }


def get_restart_context(startup_info: dict) -> str | None:
    """Generate context message about restart for injection into prompts.

    Args:
        startup_info: Result from record_startup()

    Returns:
        Context string to inject, or None if first run
    """
    previous = startup_info.get("previous_startup")
    if not previous:
        return None

    prev_time = previous.get("startup_time", "unknown")
    prev_reason = previous.get("startup_reason", "unknown")

    try:
        prev_dt = datetime.fromisoformat(prev_time)
        time_ago = datetime.now() - prev_dt

        if time_ago.total_seconds() < 60:
            time_str = f"{int(time_ago.total_seconds())} seconds ago"
        elif time_ago.total_seconds() < 3600:
            time_str = f"{int(time_ago.total_seconds() / 60)} minutes ago"
        elif time_ago.total_seconds() < 86400:
            time_str = f"{int(time_ago.total_seconds() / 3600)} hours ago"
        else:
            time_str = f"{int(time_ago.total_seconds() / 86400)} days ago"
    except (ValueError, TypeError):
        time_str = prev_time

    return (
        f"[RESTART NOTICE] You were restarted. "
        f"Previous session started {time_str} (reason: {prev_reason}). "
        f"Some context from before the restart may be lost - check your diary/state if needed."
    )


def mark_restart_reason(reason: str) -> None:
    """Update the restart reason for the next startup to read.

    Call this before initiating a restart so the new instance knows why.
    """
    state_file = get_state_file()

    if state_file.exists():
        try:
            with open(state_file) as f:
                state = json.load(f)
            state["pending_restart_reason"] = reason
            with open(state_file, "w") as f:
                json.dump(state, f, indent=2)
        except (OSError, json.JSONDecodeError):
            pass
