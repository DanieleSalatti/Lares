"""
Response handler for processing LLM responses.

Extracts tool calls and determines if Discord messages should be sent.
"""

import logging
import re
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class ParsedResponse:
    """Parsed LLM response with tool calls and optional message."""
    tool_calls: list
    discord_message: str | None
    raw_content: str


def parse_response(response_content: str) -> ParsedResponse:
    """
    Parse LLM response to extract tool calls and determine Discord message.

    The LLM can:
    1. Call discord_send_message tool explicitly -> we use that message
    2. Call other tools without discord_send_message -> no Discord message (silent work)
    3. Return plain text with no tool calls -> that text becomes the Discord message

    Args:
        response_content: Raw text content from LLM response

    Returns:
        ParsedResponse with tool_calls list and optional discord_message
    """
    tool_calls = []  # Reserved for future use
    discord_message = None

    # Check if response contains tool calls (antml:function_calls block)
    has_tool_calls = 'antml:function_calls' in response_content

    # Extract any explicit discord_send_message call content
    discord_msg_match = re.search(
        r'name="discord_send_message".*?name="content"[^>]*>([^<]+)',
        response_content,
        re.DOTALL
    )

    if discord_msg_match:
        # Explicit discord_send_message was called - use its content
        discord_message = discord_msg_match.group(1).strip()
    elif not has_tool_calls:
        # No tool calls at all - the entire response is the message
        # Strip any thinking/internal tags if present
        clean_content = response_content.strip()
        if clean_content:
            discord_message = clean_content
    # else: has tool calls but no discord_send_message -> silent (discord_message stays None)

    return ParsedResponse(
        tool_calls=tool_calls,
        discord_message=discord_message,
        raw_content=response_content
    )


def should_send_discord_message(parsed: ParsedResponse) -> bool:
    """
    Determine if we should send a Discord message.

    Returns True only if:
    - There's an explicit discord_send_message call, OR
    - There are no tool calls and there's text content
    """
    return parsed.discord_message is not None
