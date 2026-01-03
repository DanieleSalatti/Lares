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
from lares.orchestrator_factory import create_orchestrator
from lares.response_parser import parse_response
from lares.scheduler import get_scheduler
from lares.sse_consumer import (
    ApprovalResultEvent,
    DiscordClient,
    DiscordMessageEvent,
    DiscordReactionEvent,
    SchedulerChangedEvent,
    SSEConsumer,
)
from lares.time_utils import get_time_context

log = structlog.get_logger()

PERCH_INTERVAL_MINUTES = int(os.getenv("LARES_PERCH_INTERVAL_MINUTES", "30"))


class ApprovalManager:
    """Manages MCP approval workflow via Discord."""

    def __init__(self, mcp_url: str, discord: "DiscordClient"):
        self.mcp_url = mcp_url
        self.discord = discord
        self._pending: dict[int, str] = {}
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

            tool = item["tool"]
            args = item["args"]
            if isinstance(args, str):
                args = json.loads(args)

            if tool == "run_shell_command":
                cmd = args.get("command", "")
                text = f"```\n{cmd}\n```"
                title = "🔧 Shell Command Approval"
                footer = "✅ Approve  |  ❌ Deny  |  🔓 Approve & Remember"
            elif tool == "post_to_bluesky":
                post_text = args.get("text", "")
                text = f"```\n{post_text}\n```"
                title = "🦋 BlueSky Post Approval"
                footer = "✅ Approve  |  ❌ Deny"
            else:
                text = f"Tool: {tool}\nArgs: {args}"
                title = "⚠️ Tool Approval Required"
                footer = "✅ Approve  |  ❌ Deny"

            message = f"**{title}**\nID: `{approval_id}`\n\n{text}\n\n{footer}"

            result = await self.discord.send_message(message)
            if result.get("status") == "ok" and result.get("message_id"):
                msg_id = int(result["message_id"])
                self._pending[msg_id] = approval_id
                self._posted.add(approval_id)

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

        del self._pending[message_id]
        log.info("approval_handled", approval_id=approval_id, action=emoji)
        return True


class LaresCore:
    """Core Lares brain that processes events via Orchestrator."""

    def __init__(
        self,
        config,
        discord: DiscordClient,
        mcp_url: str,
        orchestrator,
    ):
        self.config = config
        self.discord = discord
        self.mcp_url = mcp_url
        self.orchestrator = orchestrator
        self.approval_manager = ApprovalManager(mcp_url, discord)
        self._current_message_id: int | None = None
        self._seen_events: set[str] = set()

    async def handle_message(self, event: DiscordMessageEvent) -> None:
        """Process a Discord message through Orchestrator."""
        event_key = f"msg:{event.message_id}"
        if event_key in self._seen_events:
            log.debug("skipping_duplicate_message", message_id=event.message_id)
            return
        self._seen_events.add(event_key)

        log.info("processing_message", author=event.author_name, content=event.content[:50])
        self._current_message_id = event.message_id

        await self.discord.typing()

        current_time = get_time_context(self.config.user.timezone)
        formatted = (
            f"Current time: {current_time}\n\n"
            f"[Discord message from {event.author_name}]: {event.content}"
        )

        try:
            await self._process_with_orchestrator(formatted)
        except Exception as e:
            log.error("orchestrator_error", error=str(e))
            await self.discord.send_message(f"Error: {e}")

    async def handle_reaction(self, event: DiscordReactionEvent) -> None:
        """Process a Discord reaction - check approvals first, then forward to Orchestrator."""
        event_key = f"react:{event.message_id}:{event.emoji}:{event.user_id}"
        if event_key in self._seen_events:
            log.debug("skipping_duplicate_reaction", message_id=event.message_id)
            return
        self._seen_events.add(event_key)

        log.info(
            "processing_reaction",
            emoji=event.emoji,
            user_id=event.user_id,
            message_id=event.message_id,
        )

        handled = await self.approval_manager.handle_reaction(
            event.message_id, event.emoji, event.user_id
        )
        if handled:
            return

        time_context = get_time_context(self.config.user.timezone)
        reaction_prompt = f"""[REACTION FEEDBACK]
{time_context}

Daniele reacted with {event.emoji} to a message.

This is lightweight feedback - no response needed unless you want to acknowledge it.
React with 👀 if you noticed, or stay silent."""

        try:
            await self._process_with_orchestrator(reaction_prompt)
        except Exception as e:
            log.error("reaction_orchestrator_failed", error=str(e))

    async def handle_approval_result(self, event: ApprovalResultEvent) -> None:
        """Process an approval result - notify Lares and Discord about the outcome."""
        log.info(
            "approval_result_received",
            approval_id=event.approval_id,
            tool=event.tool,
            status=event.status,
        )

        if event.status == "approved":
            emoji = "✅"
            if event.result and len(event.result) > 500:
                result_preview = event.result[:500] + "..."
            else:
                result_preview = event.result
            discord_msg = (
                f"{emoji} **Approval result** for `{event.tool}`:\n```\n{result_preview}\n```"
            )
            orchestrator_msg = (
                f"[TOOL RESULT - {event.tool}]\n"
                f"Status: approved\n"
                f"Result: {event.result or '(no output)'}"
            )
        elif event.status == "denied":
            emoji = "❌"
            discord_msg = f"{emoji} **Denied**: `{event.tool}` was not approved."
            orchestrator_msg = (
                f"[TOOL RESULT - {event.tool}]\n"
                f"Status: denied\n"
                f"The action was NOT executed because it was denied."
            )
        else:
            emoji = "⚠️"
            discord_msg = f"{emoji} **Error** executing `{event.tool}`: {event.result}"
            orchestrator_msg = (
                f"[TOOL RESULT - {event.tool}]\nStatus: error\nResult: {event.result}"
            )

        await self.discord.send_message(discord_msg)

        try:
            await self._process_with_orchestrator(orchestrator_msg)
        except Exception as e:
            log.error("approval_result_orchestrator_failed", error=str(e))

    async def _process_with_orchestrator(self, message: str) -> None:
        """Process a message through the Orchestrator."""
        log.info("processing_with_orchestrator")

        if hasattr(self.orchestrator, "_tool_executor_instance"):
            log.info("setting_current_message_id", message_id=self._current_message_id)
            self.orchestrator._tool_executor_instance.set_current_message_id(
                self._current_message_id
            )

        result = await self.orchestrator.process_message(message)

        if result.response_text:
            if not result.response_text.startswith("[Tool-only response:"):
                await self._execute_inline_actions(
                    result.response_text, has_tool_calls=bool(result.tool_calls_made)
                )
            else:
                log.debug("tool_only_response_skipped", tools=result.tool_calls_made)

        log.info("orchestrator_complete", iterations=result.total_iterations)

    async def _execute_inline_actions(self, content: str, has_tool_calls: bool = False) -> None:
        """Parse and execute inline Discord actions from response content."""
        actions = parse_response(content, has_tool_calls=has_tool_calls)
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
            result = await self.orchestrator.process_message(perch_prompt)

            sent_discord_message = False
            is_tool_only = result.response_text.startswith("[Tool-only response:")
            if result.response_text and not is_tool_only:
                actions = parse_response(
                    result.response_text, has_tool_calls=bool(result.tool_calls_made)
                )
                for action in actions:
                    if action.type == "react" and self._current_message_id:
                        await self.discord.react(self._current_message_id, action.emoji or "👀")
                    elif action.type in ("message", "reply"):
                        if action.content:
                            await self.discord.send_message(action.content)
                            sent_discord_message = True

            if result.tool_calls_made:
                for tc in result.tool_calls_made:
                    if tc.name == "discord_send_message":
                        sent_discord_message = True
                        break

            if not sent_discord_message:
                await self.discord.send_message("*[staying quiet]*")

            log.info("perch_time_complete", iterations=result.total_iterations)
        except Exception as e:
            log.error("perch_time_failed", error=str(e))

    async def handle_scheduled_job(self, job_id: str, prompt: str) -> None:
        """Handle a scheduled job by processing its prompt."""
        log.info("scheduled_job_fired", job_id=job_id)
        try:
            result = await self.orchestrator.process_message(prompt)
            is_tool_only = result.response_text.startswith("[Tool-only response:")
            if result.response_text and not is_tool_only:
                await self._execute_inline_actions(
                    result.response_text, has_tool_calls=bool(result.tool_calls_made)
                )
            log.info("scheduled_job_complete", job_id=job_id)
        except Exception as e:
            log.error("scheduled_job_failed", job_id=job_id, error=str(e))


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

    discord = DiscordClient(mcp_url)

    log.info("initializing_orchestrator")
    orchestrator = await create_orchestrator(
        discord=discord,
        mcp_url=mcp_url,
    )

    core = LaresCore(config, discord, mcp_url, orchestrator)

    scheduler = get_scheduler()
    scheduler.set_callback(core.handle_scheduled_job)
    scheduler.start()

    async def handle_scheduler_changed(event: SchedulerChangedEvent) -> None:
        """Reload scheduler when jobs are modified via MCP."""
        log.info("scheduler_changed_event", action=event.action, job_id=event.job_id)
        scheduler.reload_jobs()

    consumer = SSEConsumer(mcp_url)
    consumer.on_message(core.handle_message)
    consumer.on_reaction(core.handle_reaction)
    consumer.on_approval_result(core.handle_approval_result)
    consumer.on_scheduler_changed(handle_scheduler_changed)

    log.info("lares_online")

    for attempt in range(5):
        result = await discord.send_message("🦉 Lares online (MCP mode)")
        if result.get("status") == "ok":
            break
        log.warning("startup_message_failed", attempt=attempt + 1, result=result)
        await asyncio.sleep(3)

    async def poll_approvals():
        """Background task to poll for pending approvals."""
        while True:
            await core.approval_manager.poll_and_post()
            await asyncio.sleep(5)

    approval_task = asyncio.create_task(poll_approvals())

    async def perch_time_loop():
        """Background task for periodic perch time ticks."""
        await asyncio.sleep(5)
        log.info("startup_perch_tick")
        await core.perch_time_tick()

        while True:
            await asyncio.sleep(PERCH_INTERVAL_MINUTES * 60)
            await core.perch_time_tick()

    perch_task = asyncio.create_task(perch_time_loop())

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
