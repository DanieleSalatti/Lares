"""MCP-based entry point for Lares.

This is the Phase 1 architecture where Discord I/O goes through the MCP server,
and Lares Core receives events via SSE and sends responses via HTTP.
"""

import asyncio
import json
import os
import sys
from datetime import datetime

import aiohttp
import structlog

from lares.config import load_config
from lares.memory import create_letta_client, get_or_create_agent, send_message, send_tool_result
from lares.response_parser import parse_response
from lares.sse_consumer import (
    DiscordClient,
    DiscordMessageEvent,
    DiscordReactionEvent,
    SSEConsumer,
)
from lares.time_utils import get_time_context

# Async wrappers for blocking Letta SDK calls
# These run in a thread pool to avoid blocking the event loop

async def async_send_message(client, agent_id, message, retry_on_compaction=True):
    """Async wrapper for send_message - runs in thread pool."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None,
        lambda: send_message(client, agent_id, message, retry_on_compaction)
    )

async def async_send_tool_result(client, agent_id, tool_call_id, result):
    """Async wrapper for send_tool_result - runs in thread pool."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None,
        lambda: send_tool_result(client, agent_id, tool_call_id, result)
    )

from lares.tool_registry import ToolExecutor

log = structlog.get_logger()

# Configuration
PERCH_INTERVAL_MINUTES = int(os.getenv("LARES_PERCH_INTERVAL_MINUTES", "30"))


class ApprovalManager:
    """Manages MCP approval workflow via Discord."""

    def __init__(self, mcp_url: str, discord: "DiscordClient"):
        self.mcp_url = mcp_url
        self.discord = discord
        # Map Discord message_id -> approval_id
        self._pending: dict[int, str] = {}
        # Track which approval IDs we've already posted
        self._posted: set[str] = set()

    async def poll_and_post(self) -> None:
        """Poll for pending approvals and post new ones to Discord."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.mcp_url}/approvals/pending") as resp:
                    if resp.status != 200:
                        return
                    data = await resp.json()
        except Exception as e:
            log.warning("approval_poll_error", error=str(e))
            return

        for item in data.get("pending", []):
            approval_id = item["id"]
            if approval_id in self._posted:
                continue

            # Post new approval to Discord
            tool = item["tool"]
            args = item["args"]
            if isinstance(args, str):
                args = json.loads(args)

            # Format the approval message
            if tool == "run_shell_command":
                cmd = args.get("command", "")
                text = f"```\n{cmd}\n```"
                title = "🔧 Shell Command Approval"
            elif tool == "post_to_bluesky":
                post_text = args.get("text", "")
                text = f"```\n{post_text}\n```"
                title = "🦋 BlueSky Post Approval"
            else:
                text = f"Tool: {tool}\nArgs: {args}"
                title = "⚠️ Tool Approval Required"

            message = (
                f"**{title}**\n"
                f"ID: `{approval_id}`\n\n"
                f"{text}\n\n"
                f"✅ Approve  |  ❌ Deny  |  🔓 Approve & Remember"
            )

            result = await self.discord.send_message(message)
            if result.get("status") == "ok" and result.get("message_id"):
                msg_id = int(result["message_id"])
                self._pending[msg_id] = approval_id
                self._posted.add(approval_id)

                # Add reactions
                await self.discord.react(msg_id, "✅")
                await self.discord.react(msg_id, "❌")
                if tool == "run_shell_command":
                    await self.discord.react(msg_id, "🔓")

                log.info("approval_posted", approval_id=approval_id, message_id=msg_id)

    async def handle_reaction(self, message_id: int, emoji: str, user_id: int) -> bool:
        """Handle a reaction on an approval message. Returns True if handled."""
        if message_id not in self._pending:
            return False

        approval_id = self._pending[message_id]

        # Determine action based on emoji
        if emoji == "✅":
            endpoint = f"{self.mcp_url}/approvals/{approval_id}/approve"
        elif emoji == "❌":
            endpoint = f"{self.mcp_url}/approvals/{approval_id}/deny"
        elif emoji == "🔓":
            endpoint = f"{self.mcp_url}/approvals/{approval_id}/remember"
        else:
            return False

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(endpoint) as resp:
                    data = await resp.json()
                    status = data.get("status", "unknown")
                    result = data.get("result", "")
        except Exception as e:
            await self.discord.send_message(f"❌ Approval error: {e}")
            return True

        # Send result to Discord
        if emoji == "✅":
            msg = f"✅ Approved `{approval_id}`\n```\n{result[:500]}\n```"
        elif emoji == "❌":
            msg = f"❌ Denied `{approval_id}`"
        elif emoji == "🔓":
            pattern = data.get("pattern", "")
            msg = f"🔓 Approved & remembered `{pattern}`\n```\n{result[:500]}\n```"
        else:
            msg = f"Processed: {status}"

        await self.discord.send_message(msg)

        # Cleanup
        del self._pending[message_id]
        log.info("approval_handled", approval_id=approval_id, action=emoji)
        return True


class LaresCore:
    """Core Lares brain that processes events via Letta."""

    def __init__(self, config, letta_client, agent_id: str, discord: DiscordClient, mcp_url: str):
        self.config = config
        self.letta_client = letta_client
        self.agent_id = agent_id
        self.discord = discord
        self.mcp_url = mcp_url
        self.tool_executor = ToolExecutor(config.tools, letta_client, agent_id, mcp_url=mcp_url)
        self.approval_manager = ApprovalManager(mcp_url, discord)
        self._current_message_id: int | None = None
        self.max_tool_iterations = int(os.getenv("LARES_MAX_TOOL_ITERATIONS", "10"))
        self._seen_events: set[str] = set()  # Dedup SSE events

    async def handle_message(self, event: DiscordMessageEvent) -> None:
        """Process a Discord message through Letta."""
        # Dedup: skip if we've seen this message
        event_key = f"msg:{event.message_id}"
        if event_key in self._seen_events:
            log.debug("skipping_duplicate_message", message_id=event.message_id)
            return
        self._seen_events.add(event_key)

        log.info("processing_message", author=event.author_name, content=event.content[:50])
        self._current_message_id = event.message_id

        # Show typing indicator while processing
        await self.discord.typing()

        # Format message for Letta
        current_time = get_time_context(self.config.user.timezone)
        formatted = (
            f"Current time: {current_time}\n\n"
            f"[Discord message from {event.author_name}]: {event.content}"
        )

        try:
            response = await async_send_message(self.letta_client, self.agent_id, formatted)

            # Handle memory compaction
            if response.needs_retry:
                log.info("memory_compaction_during_message")
                try:
                    result_msg = await self.discord.send_message("💭 *Reorganizing my thoughts...*")
                    log.info("compaction_notification_sent", result=result_msg)
                except Exception as notify_err:
                    log.error("compaction_notification_failed", error=str(notify_err))
                response = await async_send_message(
                    self.letta_client, self.agent_id, formatted,
                    retry_on_compaction=False
                )

            await self._process_response(response)
        except Exception as e:
            log.error("letta_error", error=str(e))
            await self.discord.send_message(f"Error processing message: {e}")

    async def handle_reaction(self, event: DiscordReactionEvent) -> None:
        """Process a Discord reaction - check approvals first, then forward to Letta."""
        # Dedup: skip if we've seen this reaction
        event_key = f"react:{event.message_id}:{event.emoji}:{event.user_id}"
        if event_key in self._seen_events:
            log.debug("skipping_duplicate_reaction", message_id=event.message_id)
            return
        self._seen_events.add(event_key)

        log.info("processing_reaction", emoji=event.emoji, user_id=event.user_id, message_id=event.message_id)

        # Check if this is an approval reaction
        if await self.approval_manager.handle_reaction(event.message_id, event.emoji, event.user_id):
            return  # Handled as approval

        # Forward non-approval reactions to Letta as feedback
        # This lets me know when Daniele reacts to my messages (👍, ❤️, etc.)
        time_context = get_time_context(self.config.user.timezone)
        reaction_prompt = f"""[REACTION FEEDBACK]
{time_context}

Daniele reacted with {event.emoji} to a message.

This is lightweight feedback - no response needed unless you want to acknowledge it.
React with 👀 if you noticed, or stay silent."""

        try:
            response = await async_send_message(self.letta_client, self.agent_id, reaction_prompt)
            await self._process_response(response)
        except Exception as e:
            log.error("reaction_forward_failed", error=str(e))

    async def _process_response(self, response) -> None:
        """Process Letta response: execute actions and handle tool calls."""
        iterations = 0

        while True:
            # Process assistant text for inline actions
            if response.text:
                await self._execute_inline_actions(response.text)

            # Check for pending tool calls
            if not response.pending_tool_calls:
                break

            if iterations >= self.max_tool_iterations:
                log.warning("max_tool_iterations_reached", iterations=iterations)
                await self.discord.send_message(f"⚠️ Hit tool iteration limit ({iterations}). Stopping to avoid infinite loop.")
                break

            iterations += 1
            pending_count = len(response.pending_tool_calls)
            log.info("processing_tool_calls", iteration=iterations, count=pending_count)

            # Execute each tool call and return result to Letta
            for tool_call in response.pending_tool_calls:
                result = await self._execute_tool(tool_call.name, tool_call.arguments or {})
                log.info("tool_executed", tool=tool_call.name, result=str(result)[:100])

                try:
                    response = await async_send_tool_result(
                        self.letta_client,
                        self.agent_id,
                        tool_call.tool_call_id,
                        str(result) if result else "Done",
                    )

                    # Handle memory compaction during tool execution
                    if response.needs_retry:
                        log.info("memory_compaction_during_tool", tool=tool_call.name)
                        try:
                            result_msg = await self.discord.send_message("💭 *Reorganizing my thoughts...*")
                            log.info("compaction_notification_sent", result=result_msg)
                        except Exception as notify_err:
                            log.error("compaction_notification_failed", error=str(notify_err))
                        response = await async_send_tool_result(
                            self.letta_client,
                            self.agent_id,
                            tool_call.tool_call_id,
                            str(result) if result else "Done",
                            retry_on_compaction=False,
                        )
                except Exception as e:
                    log.error("letta_tool_response_error", error=str(e), tool=tool_call.name)
                    break

    async def _execute_inline_actions(self, content: str) -> None:
        """Parse and execute inline Discord actions from response content."""
        actions = parse_response(content)
        for action in actions:
            if action.type == "react" and self._current_message_id:
                await self.discord.react(self._current_message_id, action.emoji or "👀")
            elif action.type in ("message", "reply"):
                if action.content:
                    await self.discord.send_message(action.content)


    async def perch_time_tick(self) -> None:
        """Autonomous perch time tick - think, journal, and act."""
        log.info("perch_time_tick", timestamp=datetime.now().isoformat())

        time_context = get_time_context(self.config.user.timezone)

        perch_prompt = f"""[PERCH TIME - {datetime.now().strftime("%Y-%m-%d %H:%M")}]
{time_context}

This is your autonomous perch time tick. You have {PERCH_INTERVAL_MINUTES} minutes between ticks.

Take a moment to:
1. Reflect on recent interactions and update your memory if needed
2. Check your ideas/roadmap and consider what you could work on
3. Use your tools to make progress on a task (git operations, code changes, etc.)
4. Optionally send a message to Daniele if you have something to share

What would you like to do?"""

        try:
            response = await async_send_message(self.letta_client, self.agent_id, perch_prompt)

            if response.needs_retry:
                log.info("memory_compaction_during_perch_time")
                await self.discord.send_message("💭 *Reorganizing my thoughts...*")
                response = await async_send_message(
                    self.letta_client, self.agent_id, perch_prompt, retry_on_compaction=False
                )

            await self._process_response(response)
            log.info("perch_time_complete")

        except Exception as e:
            log.error("perch_time_failed", error=str(e))

    async def _execute_tool(self, tool_name: str, args: dict) -> str:
        """Execute a tool, routing Discord tools through MCP client."""
        # Route Discord tools through the MCP HTTP client
        if tool_name == "discord_send_message":
            result = await self.discord.send_message(
                args.get("content", ""),
                args.get("reply_to")
            )
            return result.get("status", "sent") if isinstance(result, dict) else str(result)

        if tool_name == "discord_react":
            msg_id = args.get("message_id") or self._current_message_id
            if msg_id:
                result = await self.discord.react(int(msg_id), args.get("emoji", "👀"))
                return result.get("status", "reacted") if isinstance(result, dict) else str(result)
            return "Error: No message to react to"

        # All other tools go through the tool executor
        try:
            return await self.tool_executor.execute(tool_name, args)
        except Exception as e:
            return f"Error executing {tool_name}: {e}"


async def run() -> None:
    """Main async entry point for MCP mode."""
    log.info("starting_lares_mcp_mode")

    try:
        config = load_config()
    except ValueError as e:
        print(f"Configuration error: {e}")
        sys.exit(1)

    mcp_url = os.getenv("LARES_MCP_URL", "http://localhost:8765")
    log.info("mcp_config", url=mcp_url)

    # Initialize Letta
    letta_client = create_letta_client(config)
    agent_id = await get_or_create_agent(letta_client, config)

    # Create Discord client for sending messages
    discord = DiscordClient(mcp_url)

    # Create core processor
    core = LaresCore(config, letta_client, agent_id, discord, mcp_url)

    # Create SSE consumer for receiving events
    consumer = SSEConsumer(mcp_url)
    consumer.on_message(core.handle_message)
    consumer.on_reaction(core.handle_reaction)

    # Announce we're online
    log.info("lares_online")

    # Try to send startup message (may fail if Discord isn't ready yet)
    for attempt in range(5):
        result = await discord.send_message("🦉 Lares online (MCP mode)")
        if result.get("status") == "ok":
            break
        log.warning("startup_message_failed", attempt=attempt + 1, result=result)
        await asyncio.sleep(3)

    # Start approval polling task
    async def poll_approvals():
        """Background task to poll for pending approvals."""
        while True:
            await core.approval_manager.poll_and_post()
            await asyncio.sleep(5)  # Poll every 5 seconds

    approval_task = asyncio.create_task(poll_approvals())

    # Start perch time loop
    async def perch_time_loop():
        """Background task for periodic perch time ticks."""
        # Initial tick on startup (give a few seconds for things to settle)
        await asyncio.sleep(5)
        log.info("startup_perch_tick")
        await core.perch_time_tick()

        # Then regular interval
        while True:
            await asyncio.sleep(PERCH_INTERVAL_MINUTES * 60)
            await core.perch_time_tick()

    perch_task = asyncio.create_task(perch_time_loop())

    # Run the event loop
    log.info("starting_sse_consumer", mcp_url=mcp_url)
    try:
        await consumer.run()
    finally:
        approval_task.cancel()
        perch_task.cancel()


def main() -> None:
    """Synchronous entry point."""
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        print("\nLares is going to sleep. Goodbye!")


if __name__ == "__main__":
    main()
