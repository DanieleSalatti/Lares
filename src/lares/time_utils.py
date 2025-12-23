"""Time utilities for Lares.

Handles timezone-aware time formatting so Lares always knows both
the server time (UTC) and the user's local time.
"""

from datetime import datetime
from zoneinfo import ZoneInfo

import structlog

log = structlog.get_logger()


def get_time_context(user_timezone: str = "America/Los_Angeles") -> str:
    """
    Generate a time context string showing both UTC and user's local time.

    Args:
        user_timezone: IANA timezone name (e.g., "America/Los_Angeles")

    Returns:
        A formatted string with both times for injection into messages.

    Example output:
        "Current time: Mon, Dec 23, 2025 10:15 PM (PST) / Tue, Dec 24, 2025 6:15 AM (UTC)"
    """
    now_utc = datetime.now(ZoneInfo("UTC"))

    try:
        user_tz = ZoneInfo(user_timezone)
        now_user = now_utc.astimezone(user_tz)

        # Get timezone abbreviation (PST, PDT, etc.)
        tz_abbr = now_user.strftime("%Z")

        # Format: "Mon, Dec 23, 2025 10:15 PM"
        user_time_str = now_user.strftime("%a, %b %d, %Y %I:%M %p")
        utc_time_str = now_utc.strftime("%a, %b %d, %Y %I:%M %p")

        return f"Current time: {user_time_str} ({tz_abbr}) / {utc_time_str} (UTC)"

    except Exception as e:
        log.warning("timezone_error", timezone=user_timezone, error=str(e))
        # Fallback to UTC only
        utc_time_str = now_utc.strftime("%a, %b %d, %Y %I:%M %p")
        return f"Current time: {utc_time_str} (UTC)"


def get_user_date(user_timezone: str = "America/Los_Angeles") -> str:
    """
    Get just the date in the user's timezone.

    Useful for date-sensitive greetings (holidays, etc.)

    Returns:
        Date string like "December 23, 2025"
    """
    now_utc = datetime.now(ZoneInfo("UTC"))

    try:
        user_tz = ZoneInfo(user_timezone)
        now_user = now_utc.astimezone(user_tz)
        return now_user.strftime("%B %d, %Y")
    except Exception:
        return now_utc.strftime("%B %d, %Y")


def get_user_time_of_day(user_timezone: str = "America/Los_Angeles") -> str:
    """
    Get the general time of day for the user.

    Returns one of: "morning", "afternoon", "evening", "night"
    """
    now_utc = datetime.now(ZoneInfo("UTC"))

    try:
        user_tz = ZoneInfo(user_timezone)
        now_user = now_utc.astimezone(user_tz)
        hour = now_user.hour

        if 5 <= hour < 12:
            return "morning"
        elif 12 <= hour < 17:
            return "afternoon"
        elif 17 <= hour < 21:
            return "evening"
        else:
            return "night"
    except Exception:
        return "day"  # Safe fallback
