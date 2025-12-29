"""SSE Event Consumer for receiving events from MCP server.

Part of Phase 1: Moving Discord I/O to MCP server.
"""

import asyncio
import json
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass

import aiohttp
import structlog

log = structlog.get_logger()


@dataclass
class DiscordMessageEvent:
    """A Discord message received via SSE."""

    message_id: int
    channel_id: int
    author_id: int
    author_name: str
    content: str
    timestamp: str


@dataclass
class DiscordReactionEvent:
    """A Discord reaction received via SSE."""

    message_id: int
    channel_id: int
    user_id: int
    emoji: str



@dataclass
class ApprovalEvent:
    """An approval request received via SSE."""

    approval_id: str
    tool: str
    args: dict

MessageHandler = Callable[[DiscordMessageEvent], Awaitable[None]]
ReactionHandler = Callable[[DiscordReactionEvent], Awaitable[None]]
ApprovalHandler = Callable[["ApprovalEvent"], Awaitable[None]]


class SSEConsumer:
    """Consumes Server-Sent Events from MCP server."""

    def __init__(self, mcp_url: str = "http://localhost:8765"):
        self.mcp_url = mcp_url
        self._message_handlers: list[MessageHandler] = []
        self._reaction_handlers: list[ReactionHandler] = []
        self._approval_handlers: list[ApprovalHandler] = []
        self._running = False

    def on_message(self, handler: MessageHandler) -> None:
        self._message_handlers.append(handler)

    def on_reaction(self, handler: ReactionHandler) -> None:
        self._reaction_handlers.append(handler)

    def on_approval(self, handler: ApprovalHandler) -> None:
        self._approval_handlers.append(handler)

    async def _parse_sse_stream(self, response: aiohttp.ClientResponse) -> AsyncIterator[dict]:
        buffer = ""
        async for chunk in response.content:
            buffer += chunk.decode("utf-8")
            while "\n\n" in buffer:
                event_text, buffer = buffer.split("\n\n", 1)
                event_data = {}
                for line in event_text.split("\n"):
                    if line.startswith("event:"):
                        event_data["event"] = line[6:].strip()
                    elif line.startswith("data:"):
                        event_data["data"] = line[5:].strip()
                if "data" in event_data:
                    try:
                        event_data["data"] = json.loads(event_data["data"])
                    except json.JSONDecodeError:
                        pass
                if event_data:
                    yield event_data

    async def _dispatch_event(self, event: dict) -> None:
        event_type = event.get("event", "message")
        data = event.get("data", {})

        if event_type == "discord_message" and isinstance(data, dict):
            msg = DiscordMessageEvent(
                message_id=int(data.get("message_id", 0)),
                channel_id=int(data.get("channel_id", 0)),
                author_id=int(data.get("author_id", 0)),
                author_name=data.get("author_name", ""),
                content=data.get("content", ""),
                timestamp=data.get("timestamp", ""),
            )
            for handler in self._message_handlers:
                try:
                    await handler(msg)
                except Exception as e:
                    log.error("message_handler_error", error=str(e))

        elif event_type == "discord_reaction" and isinstance(data, dict):
            react = DiscordReactionEvent(
                message_id=int(data.get("message_id", 0)),
                channel_id=int(data.get("channel_id", 0)),
                user_id=int(data.get("user_id", 0)),
                emoji=data.get("emoji", ""),
            )
            for handler in self._reaction_handlers:
                try:
                    await handler(react)
                except Exception as e:
                    log.error("reaction_handler_error", error=str(e))

        elif event_type == "approval_needed" and isinstance(data, dict):
            approval = ApprovalEvent(
                approval_id=data.get("id", ""),
                tool=data.get("tool", ""),
                args={k: v for k, v in data.items() if k not in ("id", "tool")},
            )
            for handler in self._approval_handlers:
                try:
                    await handler(approval)
                except Exception as e:
                    log.error("approval_handler_error", error=str(e))

    async def run(self, reconnect_delay: float = 5.0) -> None:
        self._running = True
        url = f"{self.mcp_url}/events"

        while self._running:
            try:
                async with aiohttp.ClientSession() as session:
                    log.info("sse_connecting", url=url)
                    async with session.get(url) as response:
                        if response.status != 200:
                            log.warning("sse_connect_failed", status=response.status)
                            await asyncio.sleep(reconnect_delay)
                            continue

                        log.info("sse_connected")
                        async for event in self._parse_sse_stream(response):
                            if not self._running:
                                break
                            await self._dispatch_event(event)

            except aiohttp.ClientError as e:
                log.error("sse_client_error", error=str(e))
            except asyncio.CancelledError:
                break
            except Exception as e:
                log.error("sse_unexpected_error", error=str(e))

            if self._running:
                await asyncio.sleep(reconnect_delay)

    def stop(self) -> None:
        self._running = False


class DiscordClient:
    """HTTP client for sending Discord messages via MCP server."""

    def __init__(self, mcp_url: str = "http://localhost:8765"):
        self.mcp_url = mcp_url

    async def send_message(self, content: str, reply_to: int | None = None) -> dict:
        """Send a message to Discord.

        Args:
            content: The message text to send
            reply_to: Optional message ID to reply to

        Returns:
            Response dict with status and message_id
        """
        url = f"{self.mcp_url}/discord/send"
        payload = {"content": content}
        if reply_to:
            payload["reply_to"] = str(reply_to)

        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload) as response:
                if response.status != 200:
                    text = await response.text()
                    return {"status": "error", "error": f"HTTP {response.status}: {text}"}
                return await response.json()

    async def typing(self) -> dict:
        """Trigger typing indicator in Discord channel.

        Typing indicator lasts ~10 seconds or until a message is sent.

        Returns:
            Response dict with status
        """
        url = f"{self.mcp_url}/discord/typing"

        async with aiohttp.ClientSession() as session:
            async with session.post(url) as response:
                if response.status != 200:
                    text = await response.text()
                    return {"status": "error", "error": f"HTTP {response.status}: {text}"}
                return await response.json()

    async def react(self, message_id: int, emoji: str) -> dict:
        """Add a reaction to a Discord message.

        Args:
            message_id: The ID of the message to react to
            emoji: The emoji to react with

        Returns:
            Response dict with status
        """
        url = f"{self.mcp_url}/discord/react"
        payload = {"message_id": str(message_id), "emoji": emoji}

        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload) as response:
                if response.status != 200:
                    text = await response.text()
                    return {"status": "error", "error": f"HTTP {response.status}: {text}"}
                return await response.json()
