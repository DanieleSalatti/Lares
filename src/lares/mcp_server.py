"""
Lares MCP Server - Portable tool layer for AI agents.

This MCP server provides all Lares tools in a framework-agnostic way.
Any MCP-compatible system (Letta, Claude Desktop, etc.) can connect to it.

Run with: python -m lares.mcp_server
Or: mcp.run(transport="sse") starts uvicorn on configured host:port

Approval endpoints:
  GET  /approvals/pending         - List pending approvals
  GET  /approvals/{id}            - Get specific approval
  POST /approvals/{id}/approve    - Approve and execute
  POST /approvals/{id}/deny       - Deny request
  GET  /health                    - Health check

Discord endpoints:
  GET  /events                    - SSE stream of Discord events
  POST /discord/send              - Send a message
  POST /discord/react             - React to a message
  POST /discord/typing            - Trigger typing indicator
"""

import asyncio
import json
import os
import subprocess
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

import discord
from discord.ext import commands
from mcp.server import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse, StreamingResponse

from lares.mcp_approval import get_queue
from lares.scheduler import get_scheduler

# Initialize MCP server
mcp = FastMCP(
    name="lares-tools",
    instructions="Lares household AI tools - shell, files, RSS, BlueSky, Obsidian",
    host="0.0.0.0",
    port=8765,
)

# Configuration
LARES_PROJECT = Path(os.getenv("LARES_PROJECT_PATH", "/home/daniele/workspace/lares"))
OBSIDIAN_VAULT = Path(
    os.getenv("OBSIDIAN_VAULT_PATH", "/home/daniele/workspace/gitlab/daniele/appunti")
)


# Load allowed directories from environment
def _load_allowed_directories() -> list[Path]:
    """Load allowed directories from LARES_ALLOWED_PATHS env var, with fallback to defaults."""
    allowed_paths = os.getenv("LARES_ALLOWED_PATHS", "")
    if allowed_paths:
        return [Path(p.strip()) for p in allowed_paths.split(":") if p.strip()]
    else:
        return [LARES_PROJECT, OBSIDIAN_VAULT]


ALLOWED_DIRECTORIES = _load_allowed_directories()
APPROVAL_DB = Path(
    os.getenv("LARES_APPROVAL_DB", "/home/daniele/workspace/lares/data/approvals.db")
)

BSKY_PUBLIC_API = "https://public.api.bsky.app/xrpc"
BSKY_AUTH_API = "https://bsky.social/xrpc"
_bsky_session_cache: dict = {}

# Initialize approval queue
approval_queue = get_queue(APPROVAL_DB)

# === DISCORD INTEGRATION ===

# Discord configuration
DISCORD_TOKEN = os.getenv("DISCORD_BOT_TOKEN", "")
DISCORD_CHANNEL_ID = int(os.getenv("DISCORD_CHANNEL_ID", "0"))
DISCORD_ENABLED = bool(DISCORD_TOKEN and DISCORD_CHANNEL_ID)

# Event queues for SSE clients (Lares Core connects here)
_event_queues: list[asyncio.Queue] = []

# Discord bot state
_discord_bot: commands.Bot | None = None
_discord_channel: discord.TextChannel | None = None


async def push_event(event_type: str, data: dict) -> None:
    """Push event to all connected SSE clients."""
    event = {
        "event": event_type,
        "data": data,
        "timestamp": datetime.now(UTC).isoformat(),
    }
    for queue in _event_queues:
        try:
            queue.put_nowait(event)
        except asyncio.QueueFull:
            pass  # Skip if queue is full


def setup_discord_bot() -> commands.Bot | None:
    """Initialize Discord bot if enabled."""
    if not DISCORD_ENABLED:
        return None

    intents = discord.Intents.default()
    intents.message_content = True
    intents.reactions = True
    bot = commands.Bot(command_prefix="!", intents=intents)

    @bot.event
    async def on_ready():
        global _discord_channel
        _discord_channel = bot.get_channel(DISCORD_CHANNEL_ID)
        if _discord_channel:
            print(f"Discord connected to #{_discord_channel.name}")
        else:
            print(f"Warning: Could not find channel {DISCORD_CHANNEL_ID}")

    @bot.event
    async def on_message(message: discord.Message):
        # Ignore own messages
        if message.author == bot.user:
            return

        # Only messages in target channel
        if message.channel.id != DISCORD_CHANNEL_ID:
            return

        # Push to SSE clients
        await push_event(
            "discord_message",
            {
                "message_id": str(message.id),
                "channel_id": str(message.channel.id),
                "author_id": str(message.author.id),
                "author_name": message.author.name,
                "content": message.content,
                "timestamp": message.created_at.isoformat(),
            },
        )

    @bot.event
    async def on_raw_reaction_add(payload: discord.RawReactionActionEvent):
        # Ignore own reactions
        if payload.user_id == bot.user.id:
            return

        message_id = str(payload.message_id)
        emoji = str(payload.emoji)

        # Push all reactions to SSE - Lares handles approval logic via API calls
        await push_event(
            "discord_reaction",
            {
                "message_id": message_id,
                "channel_id": str(payload.channel_id),
                "user_id": str(payload.user_id),
                "emoji": emoji,
            },
        )

    return bot


# Initialize Discord bot
_discord_bot = setup_discord_bot()

# Commands that can run without approval (prefix match)
SHELL_ALLOWLIST = [
    "echo ",
    "ls",
    "cat ",
    "head ",
    "tail ",
    "wc ",
    "grep ",  # Read-only
    "git status",
    "git log",
    "git diff",
    "git branch",
    "git show",  # Git read
    "git add",
    "git commit",
    "git push",
    "git pull",
    "git checkout",  # Git write
    "pytest",
    "python -m pytest",
    "ruff check",
    "ruff format",
    "mypy",  # Dev tools
    "pwd",
    "whoami",
    "date",
    "env",
    "which ",  # System info
]
# Set to True to require approval for all shell commands
SHELL_REQUIRE_ALL_APPROVAL = os.getenv("MCP_SHELL_REQUIRE_APPROVAL", "").lower() == "true"


# === HELPER FUNCTIONS ===


def is_path_allowed(path: str) -> bool:
    """Check if a path is within allowed directories."""
    try:
        target = Path(path).resolve()
        return any(
            target == allowed or allowed in target.parents
            for allowed in ALLOWED_DIRECTORIES
            if allowed.exists()
        )
    except Exception:
        return False


def _get_bsky_auth_token() -> str | None:
    """Get or refresh BlueSky auth token."""
    if "access_jwt" in _bsky_session_cache:
        return _bsky_session_cache["access_jwt"]

    handle = os.getenv("BLUESKY_HANDLE")
    password = os.getenv("BLUESKY_APP_PASSWORD")

    if not handle or not password:
        return None

    try:
        auth_url = f"{BSKY_AUTH_API}/com.atproto.server.createSession"
        data = json.dumps({"identifier": handle, "password": password}).encode()
        req = urllib.request.Request(
            auth_url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read().decode())
            _bsky_session_cache["access_jwt"] = result.get("accessJwt")
            _bsky_session_cache["did"] = result.get("did")
            return _bsky_session_cache["access_jwt"]
    except Exception:
        return None


# === APPROVAL HTTP ENDPOINTS ===


# Tools that never require approval - execute directly
NO_APPROVAL_TOOLS = {
    "memory_replace",
    "memory_search",
    "read_file",
    "list_directory",
    "read_rss_feed",
    "read_bluesky_user",
    "search_bluesky",
    "search_obsidian_notes",
    "read_obsidian_note",
    "schedule_add_job",
    "schedule_remove_job",
    "schedule_list_jobs",
}


@mcp.custom_route("/approvals", methods=["POST"])
async def create_approval(request: Request) -> JSONResponse:
    """Create a new approval request (used by ToolExecutor for commands needing approval).

    For shell commands, checks allowlist and remembered patterns first.
    If command is allowed, executes directly and returns result.
    """
    try:
        data = await request.json()
        tool = data.get("tool")
        args = data.get("args")

        if not tool or args is None:
            return JSONResponse({"error": "Missing tool or args"}, status_code=400)

        # Parse args if it's a string
        if isinstance(args, str):
            args = json.loads(args)

        # Tools that never need approval - execute directly via MCP
        if tool in NO_APPROVAL_TOOLS:
            try:
                result = await mcp.call_tool(tool, args)
                return JSONResponse(
                    {
                        "status": "auto_approved",
                        "result": str(result),
                        "reason": "Tool does not require approval",
                    }
                )
            except Exception as e:
                return JSONResponse({"error": f"Tool execution failed: {e}"}, status_code=500)

        # For shell commands, check if already allowed (allowlist or remembered)
        if tool == "run_shell_command":
            command = args.get("command", "")
            working_dir = args.get("working_dir", str(LARES_PROJECT))

            if is_shell_command_allowed(command):
                # Execute directly - no approval needed
                result = _execute_shell_command(command, working_dir)
                return JSONResponse(
                    {
                        "status": "auto_approved",
                        "result": result,
                        "reason": "Command matches allowlist or remembered pattern",
                    }
                )

        # For write_file, check if path is in allowed directories
        if tool == "write_file":
            file_path = args.get("path", "")
            if is_path_allowed(file_path):
                try:
                    result = await mcp.call_tool(tool, args)
                    return JSONResponse(
                        {
                            "status": "auto_approved",
                            "result": str(result),
                            "reason": "Path is in allowed directories",
                        }
                    )
                except Exception as e:
                    return JSONResponse({"error": f"Tool execution failed: {e}"}, status_code=500)

        # Submit to approval queue for commands that need approval
        approval_id = approval_queue.submit(tool, args)

        return JSONResponse({"id": approval_id, "status": "pending"}, status_code=202)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@mcp.custom_route("/approvals/pending", methods=["GET"])
async def get_pending_approvals(request: Request) -> JSONResponse:
    """Get all pending approval requests."""
    pending = approval_queue.get_pending()
    for item in pending:
        try:
            item["args"] = json.loads(item["args"])
        except Exception:
            pass
    return JSONResponse({"pending": pending})


@mcp.custom_route("/approvals/remembered", methods=["GET"])
async def list_remembered(request: Request) -> JSONResponse:
    """List all remembered command patterns."""
    patterns = approval_queue.get_remembered_commands()
    return JSONResponse({"patterns": patterns})


@mcp.custom_route("/approvals/{approval_id}", methods=["GET"])
async def get_approval(request: Request) -> JSONResponse:
    """Get a specific approval request by ID."""
    approval_id = request.path_params["approval_id"]
    item = approval_queue.get(approval_id)
    if not item:
        return JSONResponse({"error": "Approval not found"}, status_code=404)
    try:
        item["args"] = json.loads(item["args"])
    except Exception:
        pass
    return JSONResponse(item)


@mcp.custom_route("/approvals/{approval_id}/approve", methods=["POST"])
async def approve_request(request: Request) -> JSONResponse:
    """Approve a pending request and execute it."""
    approval_id = request.path_params["approval_id"]
    item = approval_queue.get(approval_id)

    if not item:
        return JSONResponse({"error": "Approval not found"}, status_code=404)
    if item["status"] != "pending":
        return JSONResponse({"error": f"Already {item['status']}"}, status_code=400)

    approval_queue.approve(approval_id)

    tool_name = item["tool"]
    args = json.loads(item["args"])

    # Execute using internal functions (bypass approval check)
    try:
        if tool_name == "run_shell_command":
            working_dir = args.get("working_dir", str(LARES_PROJECT))
            result_str = _execute_shell_command(args["command"], working_dir)
        elif tool_name == "write_file":
            result_str = _execute_write_file(args["path"], args["content"])
        elif tool_name == "post_to_bluesky":
            result_str = _execute_bluesky_post(args["text"])
        else:
            # Fallback for other tools (shouldn't happen often)
            result = await mcp.call_tool(tool_name, args)
            result_str = str(result)

        approval_queue.set_result(approval_id, result_str)

        # Notify Lares via SSE that approval was resolved
        await push_event(
            "approval_result",
            {
                "approval_id": approval_id,
                "tool": tool_name,
                "status": "approved",
                "result": result_str[:2000] if len(result_str) > 2000 else result_str,
            },
        )

        return JSONResponse({"status": "approved", "result": result_str})
    except Exception as e:
        error_msg = f"Execution error: {e}"
        approval_queue.set_result(approval_id, error_msg)

        await push_event(
            "approval_result",
            {"approval_id": approval_id, "tool": tool_name, "status": "error", "result": error_msg},
        )

        return JSONResponse({"status": "error", "result": error_msg})


@mcp.custom_route("/approvals/{approval_id}/deny", methods=["POST"])
async def deny_request(request: Request) -> JSONResponse:
    """Deny a pending request."""
    approval_id = request.path_params["approval_id"]
    item = approval_queue.get(approval_id)

    if not item:
        return JSONResponse({"error": "Approval not found"}, status_code=404)
    if item["status"] != "pending":
        return JSONResponse({"error": f"Already {item['status']}"}, status_code=400)

    approval_queue.deny(approval_id)

    # Notify Lares via SSE that approval was denied
    await push_event(
        "approval_result",
        {"approval_id": approval_id, "tool": item["tool"], "status": "denied", "result": None},
    )

    return JSONResponse({"status": "denied"})


@mcp.custom_route("/approvals/{approval_id}/remember", methods=["POST"])
async def approve_and_remember(request: Request) -> JSONResponse:
    """Approve and remember the command pattern for future auto-approval."""
    approval_id = request.path_params["approval_id"]
    item = approval_queue.get(approval_id)

    if not item:
        return JSONResponse({"error": "Approval not found"}, status_code=404)
    if item["status"] != "pending":
        return JSONResponse({"error": f"Already {item['status']}"}, status_code=400)

    # Only works for shell commands
    if item["tool"] != "run_shell_command":
        return JSONResponse(
            {"error": "Remember only supported for shell commands"}, status_code=400
        )

    args = item["args"]
    if isinstance(args, str):
        args = json.loads(args)

    command = args.get("command", "")
    cwd = args.get("working_dir") or str(LARES_PROJECT)

    # Add to remembered patterns
    pattern = approval_queue.add_remembered_command(command, approved_by="discord")

    # Approve the request
    approval_queue.approve(approval_id)

    # Execute the command using internal function
    result_str = _execute_shell_command(command, cwd)
    approval_queue.set_result(approval_id, result_str)
    return JSONResponse(
        {
            "status": "approved_and_remembered",
            "pattern": pattern,
            "result": result_str,
        }
    )


@mcp.custom_route("/health", methods=["GET"])
async def health_check(request: Request) -> JSONResponse:
    """Health check endpoint."""
    return JSONResponse(
        {
            "status": "ok",
            "server": "lares-mcp",
            "pending_approvals": len(approval_queue.get_pending()),
        }
    )


@mcp.custom_route("/tools", methods=["GET"])
async def list_tools_endpoint(request: Request) -> JSONResponse:
    """List all available tools with their schemas (Anthropic format)."""
    mcp_tools = await mcp.list_tools()

    # Convert MCP format to Anthropic format
    anthropic_tools = []
    for tool in mcp_tools:
        anthropic_tools.append(
            {
                "name": tool.name,
                "description": tool.description or "",
                "input_schema": tool.inputSchema,
            }
        )

    return JSONResponse({"tools": anthropic_tools})


@mcp.custom_route("/events", methods=["GET"])
async def events_endpoint(request: Request) -> StreamingResponse:
    """SSE endpoint for Lares Core to receive events (messages, reactions, etc.)."""
    queue: asyncio.Queue = asyncio.Queue(maxsize=100)
    _event_queues.append(queue)

    async def event_generator():
        try:
            while True:
                event = await queue.get()
                event_type = event.get("event", "message")
                data = event.get("data", {})
                # Proper SSE format: event type on separate line
                yield f"event: {event_type}\ndata: {json.dumps(data)}\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            if queue in _event_queues:
                _event_queues.remove(queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )


# === DISCORD HTTP ENDPOINTS ===


@mcp.custom_route("/discord/send", methods=["POST"])
async def http_discord_send(request: Request) -> JSONResponse:
    """HTTP endpoint for Lares to send Discord messages.

    Body: {"content": "message text", "reply_to": "optional_message_id"}
    """
    try:
        body = await request.json()
        content = body.get("content")
        reply_to = body.get("reply_to")

        if not content:
            return JSONResponse({"error": "content is required"}, status_code=400)

        if not _discord_channel:
            return JSONResponse({"error": "Discord not connected"}, status_code=503)

        if reply_to:
            msg = await _discord_channel.fetch_message(int(reply_to))
            sent = await msg.reply(content)
        else:
            sent = await _discord_channel.send(content)

        return JSONResponse({"status": "ok", "message_id": str(sent.id)})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@mcp.custom_route("/discord/react", methods=["POST"])
async def http_discord_react(request: Request) -> JSONResponse:
    """HTTP endpoint for Lares to add reactions to Discord messages.

    Body: {"message_id": "12345", "emoji": "👀"}
    """
    try:
        body = await request.json()
        message_id = body.get("message_id")
        emoji = body.get("emoji")

        if not message_id or not emoji:
            return JSONResponse({"error": "message_id and emoji are required"}, status_code=400)

        if not _discord_channel:
            return JSONResponse({"error": "Discord not connected"}, status_code=503)

        msg = await _discord_channel.fetch_message(int(message_id))
        await msg.add_reaction(emoji)

        return JSONResponse({"status": "ok", "emoji": emoji})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@mcp.custom_route("/discord/typing", methods=["POST"])
async def http_discord_typing(request: Request) -> JSONResponse:
    """HTTP endpoint to trigger Discord typing indicator.

    Typing indicator lasts ~10 seconds or until a message is sent.
    """
    try:
        if not _discord_channel:
            return JSONResponse({"error": "Discord not connected"}, status_code=503)

        await _discord_channel.typing()
        return JSONResponse({"status": "ok"})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


# === DISCORD TOOLS ===


@mcp.tool()
async def discord_send_message(content: str, reply_to: str | None = None) -> str:
    """Send a message to the Discord channel.

    Args:
        content: The message text to send
        reply_to: Optional message ID to reply to
    """
    if not _discord_channel:
        return "Error: Discord not connected"

    try:
        if reply_to:
            msg = await _discord_channel.fetch_message(int(reply_to))
            await msg.reply(content)
        else:
            await _discord_channel.send(content)
        return "Message sent successfully"
    except Exception as e:
        return f"Error sending message: {e}"


@mcp.tool()
async def discord_react(emoji: str, message_id: str | None = None) -> str:
    """React to a Discord message with an emoji.

    Args:
        emoji: The emoji to react with (e.g., "👀", "✅", "👍")
        message_id: Optional ID of the message to react to.
            If not provided, reacts to the current/last message.
    """
    if not _discord_channel:
        return "Error: Discord not connected"

    # If no message_id provided, we can't do anything at this layer
    # The tool executor should have provided one
    if not message_id:
        return "Error: No message_id provided and no default available"

    try:
        msg = await _discord_channel.fetch_message(int(message_id))
        await msg.add_reaction(emoji)
        return f"Reacted with {emoji}"
    except Exception as e:
        return f"Error adding reaction: {e}"


# === FILE TOOLS ===


@mcp.tool()
def read_file(path: str) -> str:
    """Read a file from the local filesystem."""
    if not is_path_allowed(path):
        return f"Error: Path not in allowed directories: {path}"
    try:
        with open(path) as f:
            return f.read()
    except FileNotFoundError:
        return f"Error: File not found: {path}"
    except Exception as e:
        return f"Error reading file: {e}"


@mcp.tool()
def list_directory(path: str) -> str:
    """List contents of a directory."""
    if not is_path_allowed(path):
        return f"Error: Path not in allowed directories: {path}"
    try:
        entries = sorted(Path(path).iterdir())
        result = []
        for entry in entries:
            prefix = "📁 " if entry.is_dir() else "📄 "
            result.append(f"{prefix}{entry.name}")
        return "\n".join(result) if result else "(empty directory)"
    except FileNotFoundError:
        return f"Error: Directory not found: {path}"
    except Exception as e:
        return f"Error listing directory: {e}"


def _execute_write_file(path: str, content: str) -> str:
    """Internal: Execute file write without path check (for approved operations)."""
    try:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            f.write(content)
        return f"Successfully wrote {len(content)} bytes to {path}"
    except Exception as e:
        return f"Error writing file: {e}"


@mcp.tool()
def write_file(path: str, content: str) -> str:
    """Write content to a file. Requires approval in production mode."""
    if not is_path_allowed(path):
        return f"Error: Path not in allowed directories: {path}"
    return _execute_write_file(path, content)


def is_shell_command_allowed(command: str) -> bool:
    """Check if a shell command can run without approval."""
    if SHELL_REQUIRE_ALL_APPROVAL:
        return False
    cmd_lower = command.strip().lower()

    # Check static allowlist
    if any(cmd_lower.startswith(allowed.lower()) for allowed in SHELL_ALLOWLIST):
        return True

    # Check remembered patterns (from 🔓 approvals)
    if approval_queue.is_command_remembered(command):
        return True

    return False


# === SHELL TOOL ===


def _execute_shell_command(command: str, working_dir: str) -> str:
    """Internal: Execute shell command without approval check."""
    try:
        result = subprocess.run(
            command, shell=True, cwd=working_dir, capture_output=True, text=True, timeout=60
        )
        output = result.stdout
        if result.stderr:
            output += f"\n[stderr]: {result.stderr}"
        return output or "(no output)"
    except subprocess.TimeoutExpired:
        return "Error: Command timed out after 60 seconds"
    except Exception as e:
        return f"Error running command: {e}"


@mcp.tool()
async def run_shell_command(command: str, working_dir: str | None = None) -> str:
    """Execute a shell command. Non-allowlisted commands require approval."""
    if working_dir and not is_path_allowed(working_dir):
        return f"Error: Working directory not allowed: {working_dir}"

    cwd = working_dir or str(LARES_PROJECT)

    # Check if command needs approval
    if not is_shell_command_allowed(command):
        approval_id = approval_queue.submit(
            "run_shell_command", {"command": command, "working_dir": cwd}
        )
        # Emit SSE event for approval notification
        await push_event(
            "approval_needed",
            {
                "id": approval_id,
                "tool": "run_shell_command",
                "command": command,
                "working_dir": cwd,
            },
        )
        return f"⏳ Command requires approval. ID: {approval_id}\nApproval request sent via SSE."

    # Allowed command - run directly
    return _execute_shell_command(command, cwd)


# === RSS TOOL ===


@mcp.tool()
def read_rss_feed(url: str, max_entries: int = 5) -> str:
    """Read and parse an RSS or Atom feed."""
    try:
        import feedparser  # type: ignore[import-untyped]
    except ImportError:
        return "Error: feedparser not installed"

    try:
        feed = feedparser.parse(url)
        if feed.bozo and not feed.entries:
            err = getattr(feed, "bozo_exception", "Unknown error")
            return f"Error parsing feed: {err}"

        feed_title = feed.feed.get("title", "Untitled Feed")
        lines = [f"📰 **{feed_title}**", ""]

        for entry in feed.entries[:max_entries]:
            title = entry.get("title", "Untitled")
            link = entry.get("link", "")
            pub = getattr(entry, "published", None) or getattr(entry, "updated", None)
            date_str = f" ({pub})" if pub else ""
            lines.append(f"• {title}{date_str}")
            if link:
                lines.append(f"  🔗 {link}")

        remaining = len(feed.entries) - max_entries
        if remaining > 0:
            lines.append(f"\n... and {remaining} more entries")
        return "\n".join(lines)
    except Exception as e:
        return f"Error reading feed: {e}"


# === BLUESKY TOOLS ===


@mcp.tool()
def read_bluesky_user(handle: str, limit: int = 5) -> str:
    """Read recent posts from a BlueSky user."""
    if not handle.endswith(".bsky.social") and "." not in handle:
        handle = f"{handle}.bsky.social"

    try:
        url = f"{BSKY_PUBLIC_API}/app.bsky.feed.getAuthorFeed?actor={handle}&limit={limit}"
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())

        posts = data.get("feed", [])
        if not posts:
            return f"No posts found for @{handle}"

        lines = [f"🦋 Recent posts from @{handle}", ""]
        for item in posts:
            post = item.get("post", {})
            record = post.get("record", {})
            text = record.get("text", "")[:200]
            created = record.get("createdAt", "")[:10]
            lines.append(f"• [{created}] {text}")
            lines.append("")
        return "\n".join(lines)
    except urllib.error.HTTPError as e:
        return f"Error: HTTP {e.code} - {e.reason}"
    except Exception as e:
        return f"Error reading BlueSky: {e}"


@mcp.tool()
def search_bluesky(query: str, limit: int = 10) -> str:
    """Search BlueSky posts for a given query. Requires authentication."""
    auth_token = _get_bsky_auth_token()
    if not auth_token:
        return "Error: Search requires auth. Set BLUESKY_HANDLE and BLUESKY_APP_PASSWORD"

    try:
        import urllib.parse

        encoded = urllib.parse.quote(query)
        url = f"{BSKY_AUTH_API}/app.bsky.feed.searchPosts?q={encoded}&limit={limit}"
        headers = {"Authorization": f"Bearer {auth_token}", "Accept": "application/json"}
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())

        posts = data.get("posts", [])
        if not posts:
            return f"No results for: {query}"

        lines = [f"🔍 Search results for: {query}", ""]
        for post in posts:
            author = post.get("author", {}).get("handle", "unknown")
            text = post.get("record", {}).get("text", "")[:150]
            lines.append(f"@{author}: {text}")
            lines.append("")
        return "\n".join(lines)
    except urllib.error.HTTPError as e:
        _bsky_session_cache.clear()
        return f"Error: HTTP {e.code} - {e.reason}"
    except Exception as e:
        return f"Error searching BlueSky: {e}"


def _execute_bluesky_post(text: str, retry: bool = True) -> str:
    """Internal: Execute BlueSky post without approval check."""
    auth_token = _get_bsky_auth_token()
    if not auth_token:
        return "Error: Auth required. Set BLUESKY_HANDLE and BLUESKY_APP_PASSWORD"

    did = _bsky_session_cache.get("did")
    if not did:
        return "Error: No DID in session. Re-authentication required."

    try:
        create_url = f"{BSKY_AUTH_API}/com.atproto.repo.createRecord"
        headers = {
            "Authorization": f"Bearer {auth_token}",
            "Content-Type": "application/json",
        }
        record = {
            "$type": "app.bsky.feed.post",
            "text": text,
            "createdAt": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        }
        payload = json.dumps(
            {
                "repo": did,
                "collection": "app.bsky.feed.post",
                "record": record,
            }
        ).encode()

        req = urllib.request.Request(create_url, data=payload, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read().decode())
        return f"✅ Posted to BlueSky!\nURI: {result.get('uri')}"
    except urllib.error.HTTPError as e:
        _bsky_session_cache.clear()
        # Retry once with fresh token on 400/401 (likely expired token)
        if retry and e.code in (400, 401):
            return _execute_bluesky_post(text, retry=False)
        return f"Error: HTTP {e.code} - {e.reason}"
    except Exception as e:
        return f"Error posting to BlueSky: {e}"


@mcp.tool()
async def post_to_bluesky(text: str) -> str:
    """Post a message to BlueSky. Requires approval."""
    if len(text) > 300:
        return f"Error: Post too long ({len(text)} chars). Maximum is 300."
    if not text.strip():
        return "Error: Post text cannot be empty."

    # BlueSky posts always require approval
    approval_id = approval_queue.submit("post_to_bluesky", {"text": text})
    # Emit SSE event for approval notification
    await push_event(
        "approval_needed",
        {
            "id": approval_id,
            "tool": "post_to_bluesky",
            "text": text,
        },
    )
    return f"🦋 BlueSky post queued for approval. ID: {approval_id}\nApproval request sent via SSE."


# === OBSIDIAN TOOLS ===


@mcp.tool()
def search_obsidian_notes(query: str, max_results: int = 10) -> str:
    """Search for notes in the Obsidian vault containing the query string."""
    if not OBSIDIAN_VAULT.exists():
        return f"Error: Obsidian vault not found at {OBSIDIAN_VAULT}"

    matches = []
    query_lower = query.lower()

    try:
        for md_file in OBSIDIAN_VAULT.rglob("*.md"):
            if any(part.startswith(".") for part in md_file.parts):
                continue
            try:
                content = md_file.read_text(encoding="utf-8")
                if query_lower in content.lower():
                    rel_path = md_file.relative_to(OBSIDIAN_VAULT)
                    count = content.lower().count(query_lower)
                    matches.append((str(rel_path), count))
            except Exception:
                continue

        if not matches:
            return f"No notes found containing: {query}"

        matches.sort(key=lambda x: x[1], reverse=True)
        lines = [f"📔 Notes matching '{query}':", ""]
        for path, count in matches[:max_results]:
            lines.append(f"• {path} ({count} match{'es' if count > 1 else ''})")

        remaining = len(matches) - max_results
        if remaining > 0:
            lines.append(f"\n... and {remaining} more notes")
        return "\n".join(lines)
    except Exception as e:
        return f"Error searching notes: {e}"


@mcp.tool()
def read_obsidian_note(path: str) -> str:
    """Read a specific note from the Obsidian vault."""
    note_path = OBSIDIAN_VAULT / path

    try:
        note_path.resolve().relative_to(OBSIDIAN_VAULT.resolve())
    except ValueError:
        return "Error: Path must be within the Obsidian vault"

    if not note_path.exists():
        return f"Error: Note not found: {path}"
    if note_path.suffix != ".md":
        return "Error: Only markdown files can be read"

    try:
        content = note_path.read_text(encoding="utf-8")
        return f"📄 {path}\n{'=' * 40}\n\n{content}"
    except Exception as e:
        return f"Error reading note: {e}"


# === MEMORY TOOLS ===


@mcp.tool()
async def memory_replace(label: str, old_str: str, new_str: str) -> str:
    """Replace part of a memory block's content.

    Args:
        label: The memory block label (persona, human, state, ideas)
        old_str: The exact text to replace
        new_str: The replacement text

    Returns:
        Success or error message
    """
    try:
        # Import here to avoid circular dependencies
        from lares.config import load_memory_config
        from lares.orchestrator_factory import create_memory_provider

        # Get memory provider
        memory_config = load_memory_config()
        memory = await create_memory_provider(
            sqlite_path=memory_config.sqlite_path,
        )

        # Get current context to find the block
        context = await memory.get_context()
        current_block = None
        for block in context.blocks:
            if block.label == label:
                current_block = block
                break

        if not current_block:
            await memory.shutdown()
            return f"Error: Memory block '{label}' not found"

        # Perform replacement
        if old_str not in current_block.value:
            await memory.shutdown()
            return f"Error: String '{old_str}' not found in memory block '{label}'"

        new_value = current_block.value.replace(old_str, new_str)
        await memory.update_block(label, new_value)
        await memory.shutdown()

        return f"Successfully updated memory block '{label}'"

    except Exception as e:
        return f"Error updating memory: {e}"


@mcp.tool()
async def memory_search(query: str, limit: int = 5) -> str:
    """Search through memory blocks and recent messages.

    Args:
        query: Text to search for
        limit: Maximum number of results to return

    Returns:
        Search results from memory
    """
    try:
        # Import here to avoid circular dependencies
        from lares.config import load_memory_config
        from lares.orchestrator_factory import create_memory_provider

        # Get memory provider
        memory_config = load_memory_config()
        memory = await create_memory_provider(
            sqlite_path=memory_config.sqlite_path,
        )

        results = await memory.search(query, limit)
        await memory.shutdown()

        if not results:
            return f"No matches found for '{query}'"

        formatted_results = []
        for result in results:
            formatted_results.append(
                f"ID: {result['id']}\n"
                f"Role: {result['role']}\n"
                f"Date: {result['created_at']}\n"
                f"Content: {result['content'][:200]}...\n"
            )

        return f"Search results for '{query}':\n\n" + "\n---\n".join(formatted_results)

    except Exception as e:
        return f"Error searching memory: {e}"


# === SCHEDULER TOOLS ===


@mcp.tool()
async def schedule_add_job(job_id: str, prompt: str, schedule: str, description: str = "") -> str:
    """Add a scheduled job.

    Args:
        job_id: Unique identifier for the job
        prompt: Message to send to agent when job fires
        schedule: Cron ("0 9 * * *"), ISO datetime, or interval ("every 2 hours")
        description: Human-readable description
    """
    scheduler = get_scheduler()
    result = scheduler.add_job(job_id, prompt, schedule, description)
    if not result.startswith("Error"):
        await push_event("scheduler_changed", {"action": "add", "job_id": job_id})
    return result


@mcp.tool()
async def schedule_remove_job(job_id: str) -> str:
    """Remove a scheduled job.

    Args:
        job_id: The job identifier to remove
    """
    scheduler = get_scheduler()
    result = scheduler.remove_job(job_id)
    if not result.startswith("Error"):
        await push_event("scheduler_changed", {"action": "remove", "job_id": job_id})
    return result


@mcp.tool()
def schedule_list_jobs() -> str:
    """List all scheduled jobs with schedules and next run times."""
    scheduler = get_scheduler()
    return scheduler.list_jobs()


# === ENTRY POINT ===


async def run_with_discord():
    """Run MCP server with Discord bot."""
    import signal

    import uvicorn

    # Start Discord bot in background if enabled
    discord_task = None
    if _discord_bot:
        print("Starting Discord bot...")
        discord_task = asyncio.create_task(_discord_bot.start(DISCORD_TOKEN))

    # Create uvicorn config with install_signal_handlers=False (we handle them)
    config = uvicorn.Config(
        mcp.sse_app(),
        host="0.0.0.0",
        port=8765,
        log_level="info",
    )
    server = uvicorn.Server(config)

    # Handle SIGTERM/SIGINT gracefully
    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()

    def handle_signal():
        print("Received shutdown signal...")
        stop_event.set()
        server.should_exit = True

    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, handle_signal)

    try:
        await server.serve()
    finally:
        print("Shutting down Discord...")
        if discord_task:
            discord_task.cancel()
            try:
                await discord_task
            except asyncio.CancelledError:
                pass
        if _discord_bot:
            await _discord_bot.close()
        print("Shutdown complete.")


if __name__ == "__main__":
    print("Starting Lares MCP Server on http://0.0.0.0:8765")
    print("Tools: read_file, list_directory, write_file, run_shell_command")
    print("       read_rss_feed, read_bluesky_user, search_bluesky, post_to_bluesky")
    print("       search_obsidian_notes, read_obsidian_note")
    print("       discord_send_message, discord_react")
    print("Endpoints: /health, /events, /approvals/pending, /approvals/{id}")
    if DISCORD_ENABLED:
        print(f"Discord: enabled (channel {DISCORD_CHANNEL_ID})")
        asyncio.run(run_with_discord())
    else:
        print("Discord: disabled (set DISCORD_BOT_TOKEN and DISCORD_CHANNEL_ID)")
        mcp.run(transport="sse")
