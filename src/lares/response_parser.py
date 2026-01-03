"""Parse agent responses into executable Discord actions.

Supports both plain text responses (backwards compatible) and
structured JSON actions for fine-grained control.

IMPORTANT: When tool calls are present without discord_send_message,
the response is considered silent (tool-only work).
"""

import json
import re
from dataclasses import dataclass


@dataclass
class DiscordAction:
    """A single action to execute on Discord."""

    type: str  # react, message, reply, silent
    emoji: str | None = None
    content: str | None = None


def parse_response(text: str | None, has_tool_calls: bool = False) -> list[DiscordAction]:
    """
    Parse agent response text into a list of Discord actions.

    Supports:
    - Plain text (no tools): treated as a reply to the triggering message
    - Tool calls without discord_send_message: silent (no Discord message)
    - Explicit discord_send_message tool: use that message content
    - JSON actions: {"actions": [{"type": "react", "emoji": "👀"}, ...]}
    - JSON in markdown code blocks: ```json {...} ```

    Args:
        text: The agent's response text
        has_tool_calls: Whether the response included tool calls

    Returns:
        List of DiscordAction objects to execute in order.
        Empty list if text is None/empty.
        Single reply action for plain text (only if no tool calls).

    Examples:
        >>> parse_response("Hello!")
        [DiscordAction(type='reply', content='Hello!')]

        >>> parse_response("Internal thought", has_tool_calls=True)
        []  # Silent because tools were used

        >>> parse_response('{"actions": [{"type": "react", "emoji": "👀"}]}')
        [DiscordAction(type='react', emoji='👀')]
    """
    if not text:
        return []

    text = text.strip()

    # Empty after stripping whitespace
    if not text:
        return []

    # Check for special markers first
    text_lower = text.lower()
    if text_lower.startswith("[silent]"):
        return [DiscordAction(type="silent")]
    if text_lower.startswith("[thinking]"):
        return [DiscordAction(type="silent")]

    # Try to extract JSON
    json_str = _extract_json(text)

    if json_str:
        actions = _parse_json_actions(json_str)
        if actions:
            return actions

    # If tool calls were made but no explicit discord_send_message,
    # treat as silent work (no Discord output)
    if has_tool_calls:
        return []

    # Plain text with no tools - treat as reply (backwards compatible)
    return [DiscordAction(type="reply", content=text)]


def _extract_json(text: str) -> str | None:
    """Extract JSON string from text, handling markdown code blocks."""
    # Try markdown code block first (```json ... ``` or ``` ... ```)
    json_match = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL)
    if json_match:
        return json_match.group(1).strip()

    # Try raw JSON object (starts with {)
    if text.startswith("{"):
        brace_count = 0
        for i, char in enumerate(text):
            if char == "{":
                brace_count += 1
            elif char == "}":
                brace_count -= 1
                if brace_count == 0:
                    return text[: i + 1]

    # Try raw JSON array (starts with [)
    if text.startswith("["):
        bracket_count = 0
        for i, char in enumerate(text):
            if char == "[":
                bracket_count += 1
            elif char == "]":
                bracket_count -= 1
                if bracket_count == 0:
                    return text[: i + 1]

    return None


def _parse_json_actions(json_str: str) -> list[DiscordAction]:
    """Parse JSON string into list of actions."""
    try:
        data = json.loads(json_str)

        # Handle both {"actions": [...]} and direct [...]
        if isinstance(data, dict):
            actions_data = data.get("actions", [])
        elif isinstance(data, list):
            actions_data = data
        else:
            return []

        actions = []
        for action_data in actions_data:
            if not isinstance(action_data, dict):
                continue

            action_type = action_data.get("type", "message")
            actions.append(
                DiscordAction(
                    type=action_type,
                    emoji=action_data.get("emoji"),
                    content=action_data.get("content"),
                )
            )

        return actions

    except json.JSONDecodeError:
        return []
