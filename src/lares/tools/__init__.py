"""Lares tools package.

Tools are organized by domain:
- filesystem: read_file, write_file
- shell: run_command
- discord: send_message, react, fetch_discord_history
- scheduler: schedule_job, remove_job, list_jobs
- rss: read_rss_feed
- bluesky: read_bluesky_user
"""

from lares.tools.base import (
    CommandNotAllowedError,
    FileBlockedError,
    InvalidToolCodeError,
    PathNotAllowedError,
    ToolError,
    ToolResult,
)
from lares.tools.bluesky import post_to_bluesky, read_bluesky_user, search_bluesky
from lares.tools.discord import (
    clear_discord_context,
    fetch_discord_history,
    react,
    send_message,
    set_discord_context,
)
from lares.tools.filesystem import (
    is_file_blocked,
    is_path_allowed,
    read_file,
    write_file,
)
from lares.tools.rss import read_rss_feed, read_rss_feeds
from lares.tools.scheduler import (
    list_jobs,
    remove_job,
    schedule_job,
)
from lares.tools.shell import add_to_allowlist, is_command_allowed, run_command
from lares.tools.system_management import restart_lares
from lares.tools.tool_creation import validate_tool_code

__all__ = [
    "ToolError",
    "CommandNotAllowedError",
    "PathNotAllowedError",
    "FileBlockedError",
    "InvalidToolCodeError",
    "ToolResult",
    "read_file",
    "write_file",
    "is_path_allowed",
    "is_file_blocked",
    "run_command",
    "is_command_allowed",
    "add_to_allowlist",
    "send_message",
    "react",
    "fetch_discord_history",
    "set_discord_context",
    "clear_discord_context",
    "schedule_job",
    "remove_job",
    "list_jobs",
    "read_rss_feed",
    "read_rss_feeds",
    "read_bluesky_user",
    "post_to_bluesky",
    "search_bluesky",
    "restart_lares",
    "validate_tool_code",
]
