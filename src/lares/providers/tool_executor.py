"""Async tool executor for the Orchestrator."""

from typing import Any, Protocol

import aiohttp
import structlog

log = structlog.get_logger()


class DiscordActions(Protocol):
    """Protocol for Discord action execution."""
    async def send_message(self, content: str) -> dict: ...
    async def react(self, message_id: int, emoji: str) -> dict: ...


class AsyncToolExecutor:
    """Routes tool calls to appropriate backends."""

    def __init__(
        self,
        discord: DiscordActions | None = None,
        mcp_url: str | None = None,
    ):
        self.discord = discord
        self.mcp_url = mcp_url
        self._current_message_id: int | None = None
        self._last_sent_message_id: int | None = None

    def set_current_message_id(self, message_id: int | None) -> None:
        self._current_message_id = message_id

    async def execute(self, tool_name: str, args: dict[str, Any]) -> str:
        """Execute a tool and return the result."""
        log.debug("tool_execute", tool=tool_name)

        # Discord actions - handle errors gracefully to prevent retry loops
        if tool_name == "discord_send_message":
            if not self.discord:
                return "Discord not available - message not sent"
            try:
                result = await self.discord.send_message(args.get("content", ""))
                if isinstance(result, dict):
                    if result.get("status") == "ok":
                        # Store the message ID for potential reactions
                        if result.get("message_id"):
                            self._last_sent_message_id = int(result["message_id"])
                            return f"Message sent successfully (ID: {result['message_id']})"
                        return "Message sent successfully"
                    else:
                        # Return error but indicate no retry needed
                        error = result.get("error", "unknown error")
                        log.warning("discord_send_failed", error=error)
                        return f"Message delivery failed ({error}). Do not retry."
                return "Message sent"
            except Exception as e:
                log.error("discord_send_exception", error=str(e))
                return f"Message failed ({e}). Do not retry."

        if tool_name == "discord_react":
            if not self.discord:
                return "Discord not available - reaction not added"

            # Check if we should use provided message_id or our tracked ones
            provided_id = args.get("message_id")

            # If we have a current message (reacting to user's message), prefer that
            # over any ID that Claude might have made up
            if self._current_message_id:
                msg_id = self._current_message_id
                log.info(
                    "discord_react_using_current",
                    provided=provided_id,
                    current=self._current_message_id,
                    using=msg_id
                )
            elif self._last_sent_message_id:
                # Use last sent if we just sent a message
                msg_id = self._last_sent_message_id
                log.info(
                    "discord_react_using_last_sent",
                    provided=provided_id,
                    last_sent=self._last_sent_message_id,
                    using=msg_id
                )
            elif provided_id:
                # Only use provided ID as last resort (might be from conversation context)
                try:
                    msg_id = int(provided_id)
                    log.info("discord_react_using_provided", provided=provided_id, using=msg_id)
                except (ValueError, TypeError):
                    msg_id = None
            else:
                msg_id = None

            if not msg_id:
                return "No message to react to"

            try:
                emoji = args.get("emoji", "👀")
                log.info("attempting_discord_react", message_id=msg_id, emoji=emoji)
                result = await self.discord.react(msg_id, emoji)
                if isinstance(result, dict):
                    if result.get("status") == "ok":
                        return "Reaction added"
                    else:
                        error = result.get("error", "unknown error")
                        return f"Reaction failed ({error}). Do not retry."
                return "Reacted"
            except Exception as e:
                log.error("discord_react_exception", error=str(e))
                return f"Reaction failed ({e}). Do not retry."

        # All other tools go through MCP (which handles approval logic)
        if self.mcp_url:
            return await self._call_mcp(tool_name, args)

        return f"Tool '{tool_name}' not executed - MCP not configured"

    async def _call_mcp(self, tool_name: str, args: dict[str, Any]) -> str:
        """Call MCP server to execute or queue a tool.

        MCP handles approval logic: auto-approves safe tools, queues others.
        """
        try:
            async with aiohttp.ClientSession() as session:
                payload = {"tool": tool_name, "args": args}
                async with session.post(f"{self.mcp_url}/approvals", json=payload) as resp:
                    data = await resp.json()
                    if resp.status == 200:
                        return data.get("result", "OK")
                    elif resp.status == 202:
                        approval_id = data.get("id") or data.get("approval_id", "unknown")
                        log.info("tool_queued_for_approval", tool=tool_name, id=approval_id)
                        return (
                            f"⏳ PENDING APPROVAL (ID: {approval_id}) - "
                            "This action requires approval before it executes. "
                            "Do NOT assume it completed - wait for approval."
                        )
                    else:
                        log.error("mcp_tool_error", tool=tool_name, status=resp.status, data=data)
                        return data.get("error", f"MCP error: {resp.status}")
        except aiohttp.ClientError as e:
            log.error("mcp_connection_error", tool=tool_name, error=str(e))
            return f"Connection error: {e}"
        except Exception as e:
            log.error("mcp_tool_exception", tool=tool_name, error=str(e))
            return f"Error: {e}"
