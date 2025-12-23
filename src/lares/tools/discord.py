"""Discord interaction tools.

These tools give the agent control over Discord output,
allowing it to send messages, react with emoji, or stay silent.
"""

from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    import discord

log = structlog.get_logger()

# Global references set by the bot at runtime
_discord_channel: "discord.TextChannel | None" = None
_discord_client: "discord.Client | None" = None
_current_message: "discord.Message | None" = None


def set_discord_context(
    channel: "discord.TextChannel",
    client: "discord.Client",
    message: "discord.Message | None" = None,
) -> None:
    """Set the Discord context for tools to use."""
    global _discord_channel, _discord_client, _current_message
    _discord_channel = channel
    _discord_client = client
    _current_message = message


def clear_discord_context() -> None:
    """Clear the Discord context after processing."""
    global _discord_channel, _discord_client, _current_message
    _discord_channel = None
    _discord_client = None
    _current_message = None


async def send_message(content: str, reply: bool = False) -> str:
    """
    Send a message to Discord.

    Args:
        content: The message text to send
        reply: If True and there's a current message, reply to it

    Returns:
        Success or error message
    """
    if _discord_channel is None:
        return "Error: No Discord channel available"

    try:
        if reply and _current_message is not None:
            await _current_message.reply(content)
            log.info("discord_reply_sent", preview=content[:50])
        else:
            await _discord_channel.send(content)
            log.info("discord_message_sent", preview=content[:50])
        return "Message sent successfully"
    except Exception as e:
        log.error("discord_send_failed", error=str(e))
        return f"Error sending message: {e}"


async def react(emoji: str) -> str:
    """
    Add an emoji reaction to the current message.

    Args:
        emoji: The emoji to react with (e.g., "👍", "✅", "🎉")

    Returns:
        Success or error message
    """
    if _current_message is None:
        return "Error: No message to react to"

    try:
        await _current_message.add_reaction(emoji)
        log.info("discord_reaction_added", emoji=emoji)
        return f"Reacted with {emoji}"
    except Exception as e:
        log.error("discord_react_failed", error=str(e), emoji=emoji)
        return f"Error adding reaction: {e}"


async def fetch_discord_history(limit: int = 20) -> str:
    """
    Fetch recent messages from the Discord channel.

    Args:
        limit: Maximum number of messages to fetch (default 20, max 100)

    Returns:
        Formatted string of recent messages
    """
    if _discord_channel is None:
        return "Error: No Discord channel available"

    # Cap at 100 to prevent excessive fetching
    limit = min(limit, 100)

    try:
        messages = []
        async for msg in _discord_channel.history(limit=limit):
            # Skip bot's own messages for cleaner history
            timestamp = msg.created_at.strftime("%Y-%m-%d %H:%M")
            author = msg.author.display_name
            content = msg.content[:200]  # Truncate long messages
            if len(msg.content) > 200:
                content += "..."
            messages.append(f"[{timestamp}] {author}: {content}")

        # Reverse to show oldest first
        messages.reverse()

        log.info("discord_history_fetched", count=len(messages))
        return "\n".join(messages) if messages else "No messages found"
    except Exception as e:
        log.error("discord_history_failed", error=str(e))
        return f"Error fetching history: {e}"
