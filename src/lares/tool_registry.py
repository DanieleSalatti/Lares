"""Registry for Letta tools with client-side execution."""

import asyncio
from typing import Any

import discord
import structlog
from letta_client import Letta

from lares.config import ToolsConfig
from lares.obsidian import read_note as obsidian_read_note, search_notes as obsidian_search_notes
from lares.tools import (
    CommandNotAllowedError,
    FileBlockedError,
    InvalidToolCodeError,
    PathNotAllowedError,
    add_to_allowlist,
    list_jobs,
    react,
    read_bluesky_user,
    read_file,
    read_rss_feed,
    remove_job,
    restart_lares,
    run_command,
    schedule_job,
    search_bluesky,
    send_message,
    validate_tool_code,
    write_file,
)

log = structlog.get_logger()

# Pending command approvals: message_id -> (command, future)
_pending_command_approvals: dict[int, tuple[str, asyncio.Future[bool]]] = {}
# Pending BlueSky posts: message_id -> (text, channel)
_pending_bluesky_posts: dict[int, tuple[str, discord.TextChannel]] = {}


async def request_command_approval(
    channel: discord.TextChannel,
    command: str,
) -> tuple[discord.Message, asyncio.Future[bool]]:
    """Request approval for a shell command not in the allowlist."""
    embed = discord.Embed(
        title="🔐 Command Approval Requested",
        description=f"```\n{command}\n```",
        color=discord.Color.orange(),
    )
    embed.add_field(
        name="This command is not in the allowlist",
        value="✅ Approve (adds to allowlist)  |  ❌ Deny",
        inline=False,
    )

    message = await channel.send(embed=embed)
    await message.add_reaction("✅")
    await message.add_reaction("❌")

    future: asyncio.Future[bool] = asyncio.get_event_loop().create_future()
    _pending_command_approvals[message.id] = (command, future)

    log.info("command_approval_requested", message_id=message.id, command=command)
    return message, future


async def request_bluesky_approval(
    channel: discord.TextChannel,
    text: str,
) -> discord.Message:
    """Request approval for a BlueSky post."""
    embed = discord.Embed(
        title="🦋 BlueSky Post Approval Requested",
        description=f"```\n{text}\n```",
        color=discord.Color.blue(),
    )
    embed.add_field(
        name="Approve this post?",
        value="✅ Approve and post  |  ❌ Deny and discard",
        inline=False,
    )
    embed.set_footer(text=f"Character count: {len(text)}/300")

    message = await channel.send(embed=embed)
    await message.add_reaction("✅")
    await message.add_reaction("❌")

    # Store the pending post (no future needed for async)
    _pending_bluesky_posts[message.id] = (text, channel)

    return message


async def handle_approval_reaction(
    message_id: int,
    emoji: str,
    user: discord.User,
) -> tuple[bool, str] | None:
    """
    Handle a reaction on an approval request.

    Returns (approved, command/text) if this was a pending approval, None otherwise.
    """
    # Check for command approvals
    if message_id in _pending_command_approvals:
        command, future = _pending_command_approvals.pop(message_id)

        if str(emoji) == "✅":
            log.info("command_approved", message_id=message_id, user=str(user), command=command)
            future.set_result(True)
            return (True, command)
        elif str(emoji) == "❌":
            log.info("command_denied", message_id=message_id, user=str(user), command=command)
            future.set_result(False)
            return (False, command)

        # Put it back if it was a different emoji
        _pending_command_approvals[message_id] = (command, future)
        return None

    # Check for BlueSky post approvals
    if message_id in _pending_bluesky_posts:
        text, channel = _pending_bluesky_posts.pop(message_id)

        if str(emoji) == "✅":
            log.info("bluesky_post_approved", message_id=message_id, user=str(user))
            # Actually post to BlueSky
            from lares.tools.bluesky import post_to_bluesky
            result = post_to_bluesky(text)

            # Send confirmation to channel
            await channel.send(f"✅ BlueSky post approved by {user.mention}!\n{result}")
            return (True, text)

        elif str(emoji) == "❌":
            log.info("bluesky_post_denied", message_id=message_id, user=str(user))
            await channel.send(f"❌ BlueSky post denied by {user.mention}")
            return (False, text)

        # Put it back if it was a different emoji
        _pending_bluesky_posts[message_id] = (text, channel)
        return None

    return None


class ToolExecutor:
    """Executes tools with approval workflow support."""

    def __init__(
        self,
        tools_config: ToolsConfig,
        letta_client: Letta | None = None,
        agent_id: str | None = None,
        discord_channel: discord.TextChannel | None = None,
    ):
        self.config = tools_config
        self.letta_client = letta_client
        self.agent_id = agent_id
        self.channel = discord_channel

    def set_channel(self, channel: discord.TextChannel) -> None:
        """Set the Discord channel for approval requests."""
        self.channel = channel

    def set_letta_context(self, client: Letta, agent_id: str) -> None:
        """Set the Letta client and agent ID for tool creation."""
        self.letta_client = client
        self.agent_id = agent_id

    async def execute(self, tool_name: str, arguments: dict[str, Any]) -> str:
        """Execute a tool and return the result as a string for Letta."""
        try:
            if tool_name == "run_command":
                return await self._run_command(
                    arguments.get("command", ""),
                    arguments.get("working_dir"),
                )
            elif tool_name == "read_file":
                return self._read_file(arguments.get("path", ""))
            elif tool_name == "write_file":
                return self._write_file(
                    arguments.get("path", ""),
                    arguments.get("content", ""),
                )
            elif tool_name == "create_tool":
                return self._create_tool(arguments.get("source_code", ""))
            elif tool_name == "schedule_job":
                return self._schedule_job(
                    arguments.get("job_id", ""),
                    arguments.get("prompt", ""),
                    arguments.get("schedule", ""),
                    arguments.get("description", ""),
                )
            elif tool_name == "remove_job":
                return self._remove_job(arguments.get("job_id", ""))
            elif tool_name == "list_jobs":
                return self._list_jobs()
            elif tool_name == "read_rss_feed":
                return self._read_rss_feed(
                    arguments.get("url", ""),
                    arguments.get("max_entries", 5),
                )
            elif tool_name == "read_bluesky_user":
                return self._read_bluesky_user(
                    arguments.get("handle", ""),
                    arguments.get("limit", 5),
                )
            elif tool_name == "search_bluesky":
                return self._search_bluesky(
                    arguments.get("query", ""),
                    arguments.get("limit", 10),
                )
            elif tool_name == "post_to_bluesky":
                return await self._post_to_bluesky(
                    arguments.get("text", ""),
                )
            elif tool_name == "discord_send_message":
                return await self._discord_send_message(
                    arguments.get("content", ""),
                    arguments.get("reply", False),
                )
            elif tool_name == "discord_react":
                return await self._discord_react(arguments.get("emoji", ""))
            elif tool_name == "restart_lares":
                return await self._restart_lares()
            elif tool_name == "search_obsidian_notes":
                return self._search_obsidian_notes(
                    arguments.get("query", ""),
                    arguments.get("max_results", 10),
                )
            elif tool_name == "read_obsidian_note":
                path = arguments.get("path", "")
                log.info("read_obsidian_note_called", path=path, args=arguments)
                result = self._read_obsidian_note(path)
                log.info("read_obsidian_note_result", path=path, result_len=len(result), result_preview=result[:100] if result else None)
                return result
            else:
                return f"Unknown tool: {tool_name}"
        except Exception as e:
            log.error("tool_execution_error", tool=tool_name, error=str(e))
            return f"Error executing {tool_name}: {e}"

    async def _run_command(self, command: str, working_dir: str | None) -> str:
        """Execute a command, requesting approval if needed."""
        try:
            result = run_command(
                command,
                self.config.command_allowlist,
                working_dir,
            )
            output = str(result["stdout"])
            if result["stderr"]:
                output += f"\n[stderr]: {result['stderr']}"
            if result["returncode"] != 0:
                output += f"\n[exit code: {result['returncode']}]"
            return output

        except CommandNotAllowedError:
            # Request approval
            if self.channel is None:
                return f"Command not allowed and no Discord channel for approval: {command}"

            log.info("requesting_command_approval", command=command)

            _, future = await request_command_approval(self.channel, command)

            try:
                # Wait for approval (timeout after 5 minutes)
                approved = await asyncio.wait_for(future, timeout=300)

                if approved:
                    # Add to allowlist and retry
                    add_to_allowlist(
                        command,
                        self.config.allowlist_file,
                        self.config.command_allowlist,
                    )
                    await self.channel.send("✅ Command approved and added to allowlist!")

                    # Now run it
                    result = run_command(
                        command,
                        self.config.command_allowlist,
                        working_dir,
                    )
                    output = str(result["stdout"])
                    if result["stderr"]:
                        output += f"\n[stderr]: {result['stderr']}"
                    return output
                else:
                    return (
                        f"Command denied by Daniele: {command}\n\n"
                        "(Daniele saw this request and chose to deny it)"
                    )

            except TimeoutError:
                await self.channel.send(
                    f"⏰ Approval request timed out for: `{command}`\n"
                    "Lares has been notified."
                )
                return (
                    f"Approval request timed out after 5 minutes for command: {command}\n\n"
                    "(Daniele has been notified of the timeout)"
                )

    def _read_file(self, path: str) -> str:
        """Read a file."""
        try:
            return read_file(path, self.config.allowed_paths, self.config.blocked_files)
        except PathNotAllowedError:
            return f"Error: Path not in allowed directories: {path}"
        except FileBlockedError:
            return f"Error: File is blocked (may contain secrets): {path}"

    def _write_file(self, path: str, content: str) -> str:
        """Write a file."""
        try:
            return write_file(
                path, content, self.config.allowed_paths, self.config.blocked_files
            )
        except PathNotAllowedError:
            return f"Error: Path not in allowed directories: {path}"
        except FileBlockedError:
            return f"Error: File is blocked (may contain secrets): {path}"

    def _create_tool(self, source_code: str) -> str:
        """Create a new tool from Python source code."""
        if not self.letta_client or not self.agent_id:
            return "Error: Letta client not configured for tool creation"

        # Validate the source code
        try:
            func_name, docstring = validate_tool_code(source_code)
        except InvalidToolCodeError as e:
            return f"Error: {e}"

        # Register the tool with Letta
        try:
            tool = self.letta_client.tools.upsert(
                source_code=source_code,
                default_requires_approval=False,  # Lares-created tools run in sandbox
            )

            # Attach to agent
            try:
                self.letta_client.agents.tools.attach(
                    agent_id=self.agent_id, tool_id=tool.id
                )
            except Exception:
                # May already be attached (update case)
                pass

            log.info("tool_created", name=func_name, tool_id=tool.id)
            return f"Successfully created tool '{func_name}': {docstring[:100]}..."

        except Exception as e:
            log.error("tool_creation_failed", name=func_name, error=str(e))
            return f"Error creating tool: {e}"

    def _schedule_job(
        self, job_id: str, prompt: str, schedule: str, description: str
    ) -> str:
        """Schedule a job."""
        return schedule_job(job_id, prompt, schedule, description)

    def _remove_job(self, job_id: str) -> str:
        """Remove a scheduled job."""
        return remove_job(job_id)

    def _list_jobs(self) -> str:
        """List all scheduled jobs."""
        return list_jobs()

    def _read_rss_feed(self, url: str, max_entries: int) -> str:
        """Read an RSS feed."""
        return read_rss_feed(url, max_entries=max_entries)

    def _read_bluesky_user(self, handle: str, limit: int) -> str:
        """Read posts from a Bluesky user."""
        return read_bluesky_user(handle, limit=limit)

    def _search_bluesky(self, query: str, limit: int) -> str:
        """Search Bluesky posts."""
        return search_bluesky(query, limit=limit)

    async def _post_to_bluesky(self, text: str) -> str:
        """Post to BlueSky with approval workflow."""
        if self.channel is None:
            return "Error: No Discord channel available for BlueSky post approval"

        log.info("requesting_bluesky_approval", text_length=len(text))

        # Request approval
        message = await request_bluesky_approval(self.channel, text)

        return (
            f"📨 BlueSky post queued for approval (message #{message.id})\n"
            f"The post will be sent once approved by reacting with ✅\n"
            f"Text: {text[:100]}{'...' if len(text) > 100 else ''}"
        )

    async def _discord_send_message(self, content: str, reply: bool) -> str:
        """Send a message to Discord."""
        return await send_message(content, reply=reply)

    async def _discord_react(self, emoji: str) -> str:
        """React to the current message with an emoji."""
        return await react(emoji)

    async def _restart_lares(self) -> str:
        """Restart the Lares service."""
        return await restart_lares()

    def _search_obsidian_notes(self, query: str, max_results: int) -> str:
        """Search notes in the Obsidian vault."""
        return obsidian_search_notes(query, max_results=max_results)

    def _read_obsidian_note(self, path: str) -> str:
        """Read a specific note from the Obsidian vault."""
        log.info("_read_obsidian_note_wrapper", path=path)
        result = obsidian_read_note(path)
        log.info("_read_obsidian_note_wrapper_result", path=path, result_len=len(result) if result else 0, result_preview=result[:100] if result else None)
        return result


# Tool definitions for Letta registration
TOOL_SOURCES = {
    "run_command": '''
def run_command(command: str, working_dir: str = None) -> str:
    """
    Execute a shell command on the local machine.

    Use this for: git operations, running tests, checking code with linters.
    Common commands: git status, git push, pytest, ruff check, mypy, ls, cat.
    Commands not in the allowlist will require human approval.

    Args:
        command: The shell command to execute
        working_dir: Working directory (optional, defaults to project root)

    Returns:
        Command output (stdout and stderr)
    """
    raise Exception("Client-side tool")
''',
    "read_file": '''
def read_file(path: str) -> str:
    """
    Read a file from the local filesystem.

    Use this to examine source code, read documentation, or check configs.
    Only files in allowed paths can be read.
    Sensitive files (.env, credentials) are blocked.

    Args:
        path: Absolute path to the file to read

    Returns:
        File contents as a string
    """
    raise Exception("Client-side tool")
''',
    "write_file": '''
def write_file(path: str, content: str) -> str:
    """
    Write content to a file on the local filesystem.

    Use this to create or modify source code, documentation, or configuration.
    Only files in allowed paths can be written. Sensitive files are blocked.

    Args:
        path: Absolute path to the file to write
        content: Content to write to the file

    Returns:
        Success or error message
    """
    raise Exception("Client-side tool")
''',
    "create_tool": '''
def create_tool(source_code: str) -> str:
    """
    Create a new tool from Python source code.

    Use this to extend your own capabilities by creating new tools.
    The last top-level function becomes the tool entry point and must have a docstring.
    Helper functions are allowed and encouraged for clean, modular code.
    Import statements are not allowed - tools run in Letta's sandbox.

    IMPORTANT: This tool requires human approval before execution.

    Args:
        source_code: Python code with the main function last (helpers allowed)

    Returns:
        Success message with tool name, or error description
    """
    raise Exception("Client-side tool")
''',
    "schedule_job": '''
def schedule_job(job_id: str, prompt: str, schedule: str, description: str = "") -> str:
    """
    Schedule a job to trigger with a prompt at specified times.

    Use this to set reminders, recurring tasks, or timed notifications.
    Jobs are checked during perch time ticks.

    Args:
        job_id: Unique identifier for the job (used to remove it later)
        prompt: The prompt/message to send when the job triggers
        schedule: When to run:
            - ISO datetime for one-time: "2025-12-25T09:00:00"
            - Simple intervals: "every 2 hours", "every day at 9:00"
        description: Human-readable description of what this job does

    Returns:
        Success or error message
    """
    raise Exception("Client-side tool")
''',
    "remove_job": '''
def remove_job(job_id: str) -> str:
    """
    Remove a scheduled job.

    Args:
        job_id: The ID of the job to remove

    Returns:
        Success or error message
    """
    raise Exception("Client-side tool")
''',
    "list_jobs": '''
def list_jobs() -> str:
    """
    List all scheduled jobs.

    Returns:
        Formatted list of jobs with their schedules and descriptions
    """
    raise Exception("Client-side tool")
''',
    "read_rss_feed": '''
def read_rss_feed(url: str, max_entries: int = 5) -> str:
    """
    Read and parse an RSS or Atom feed from the given URL.

    Use this to monitor news, blogs, or any site with an RSS feed.
    Great for staying updated on topics of interest.

    Args:
        url: The URL of the RSS/Atom feed to read
        max_entries: Maximum number of entries to return (default 5)

    Returns:
        Formatted string containing feed entries with titles, dates, and summaries
    """
    raise Exception("Client-side tool")
''',
    "read_bluesky_user": '''
def read_bluesky_user(handle: str, limit: int = 5) -> str:
    """
    Read recent posts from a BlueSky user.

    Use this to check what someone is posting about on BlueSky.
    No authentication required for public posts.

    Args:
        handle: The user's handle (e.g., "user.bsky.social" or just "username")
        limit: Maximum number of posts to return (default 5)

    Returns:
        Formatted string containing the user's recent posts
    """
    raise Exception("Client-side tool")
''',
    "search_bluesky": '''
def search_bluesky(query: str, limit: int = 10) -> str:
    """
    Search BlueSky posts for a given query.

    Use this to find posts about specific topics on BlueSky.
    Searches public posts only.

    Args:
        query: Search query string
        limit: Maximum number of results (default 10)

    Returns:
        Formatted string containing matching posts
    """
    raise Exception("Client-side tool")
''',
    "post_to_bluesky": '''
def post_to_bluesky(text: str) -> str:
    """
    Post a message to BlueSky.

    Use this to share thoughts, interesting finds, or engage on BlueSky.
    Posts appear on your account (@laresai.bsky.social).

    Be thoughtful about what you post - it represents you publicly.

    Args:
        text: The text to post (max 300 characters)

    Returns:
        Status message indicating success or failure
    """
    raise Exception("Client-side tool")
''',

    "discord_send_message": '''
def discord_send_message(content: str, reply: bool = False) -> str:
    """
    Send a message to the Discord channel.

    Use this to communicate with Daniele. You can send updates, ask questions,
    share findings, or just chat.

    Args:
        content: The message text to send
        reply: If True, reply to the triggering message (default False)

    Returns:
        Success or error message
    """
    raise Exception("Client-side tool")
''',
    "discord_react": '''
def discord_react(emoji: str) -> str:
    """
    React to the current message with an emoji.

    Use this to acknowledge messages, show emotions, or give quick feedback.
    Common emojis: 👀 (looking), ✅ (done), 👍 (ok), ❤️ (love), 🎉 (celebrate)

    Args:
        emoji: The emoji to react with (e.g., "👀", "✅", "👍")

    Returns:
        Success or error message
    """
    raise Exception("Client-side tool")
''',
    "restart_lares": '''
def restart_lares() -> str:
    """
    Restart the Lares systemd service.

    Use this when:
    - Updates have been applied via git pull and need to take effect
    - Configuration changes (.env) require a restart
    - You want to perform periodic maintenance (clear memory, fresh start)
    - Recovery from suspected issues or unusual behavior

    This requires passwordless sudo access to be configured.
    Run scripts/setup-sudoers.sh during installation.

    Note: Lares will exit immediately and systemd will automatically restart it.
    You will be offline for a few seconds during the restart.

    Returns:
        Success message (though you'll restart before seeing it)
    """
    raise Exception("Client-side tool")
''',
    "search_obsidian_notes": '''
def search_obsidian_notes(query: str, max_results: int = 10) -> str:
    """
    Search for notes in the Obsidian vault containing the query string.

    Use this to find relevant notes, discover connections between topics,
    or look up information from past notes.

    Args:
        query: Text to search for (case-insensitive)
        max_results: Maximum number of matching notes to return (default 10)

    Returns:
        Formatted string with matching notes and context snippets
    """
    raise Exception("Client-side tool")
''',
    "read_obsidian_note": '''
def read_obsidian_note(path: str) -> str:
    """
    Read a specific note from the Obsidian vault.

    Use this to read the full content of a note found via search,
    or to access a known note by path.

    Args:
        path: Path to the note relative to vault root (e.g., "Diario/2025/01/2025-01-12.md")

    Returns:
        The full content of the note, or an error message if not found
    """
    raise Exception("Client-side tool")
''',
}


def register_tools_with_letta(client: Letta, agent_id: str) -> list[str]:
    """
    Register client-side tools with a Letta agent.

    Tools are created with defaultRequiresApproval based on whether they
    need user approval or can be auto-executed.

    Returns list of registered tool names.
    """
    log.info("registering_tools", agent_id=agent_id)

    # Whitelist of tools that DON'T need user approval (auto-executed)
    TOOLS_NOT_REQUIRING_USER_APPROVAL = {
        "run_command",  # Has internal allowlist + Discord approval workflow
        "post_to_bluesky",  # Has Discord approval workflow
        "discord_send_message",
        "discord_react",
        "read_file",
        "write_file",
        "schedule_job",
        "remove_job",
        "list_jobs",
        "read_rss_feed",
        "read_bluesky_user",
        "search_bluesky",
        "search_obsidian_notes",
        "read_obsidian_note",
        "restart_lares",
    }

    registered: list[str] = []
    tool_ids: list[str] = []

    for name, source_code in TOOL_SOURCES.items():
        try:
            # Tools NOT in whitelist require approval (safer default)
            needs_approval = name not in TOOLS_NOT_REQUIRING_USER_APPROVAL

            tool = client.tools.upsert(
                source_code=source_code,
                default_requires_approval=needs_approval,
            )
            log.info("tool_registered", name=name, tool_id=tool.id, requires_approval=needs_approval)
            registered.append(name)
            tool_ids.append(tool.id)
        except Exception as e:
            log.error("tool_registration_failed", name=name, error=str(e))

    # Attach tools to the agent
    for tool_id in tool_ids:
        try:
            client.agents.tools.attach(agent_id=agent_id, tool_id=tool_id)
            log.info("tool_attached_to_agent", tool_id=tool_id, agent_id=agent_id)
        except Exception as e:
            # May already be attached
            log.warning("tool_attach_failed", tool_id=tool_id, error=str(e))

    return registered
