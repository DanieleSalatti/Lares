# Discord Actions (Strix-style Output)

## Overview

Allow the agent to return structured actions instead of plain text responses.
This enables patterns like: react 👀 → do work → react ✅ → send message.

## Response Format

The agent can return either:
1. **Plain text** - sent as a reply (backwards compatible)
2. **JSON actions** - parsed and executed in order

### JSON Format

```json
{
  "actions": [
    {"type": "react", "emoji": "👀"},
    {"type": "message", "content": "Working on it..."},
    {"type": "react", "emoji": "✅"}
  ]
}
```

### Action Types

| Type | Fields | Description |
|------|--------|-------------|
| `react` | `emoji` | Add reaction to the triggering message |
| `message` | `content` | Send a message to the channel |
| `reply` | `content` | Reply to the triggering message |
| `silent` | - | Do nothing (explicit no-op) |

## Implementation

### 1. Response Parser (`src/lares/response_parser.py`)

```python
import json
import re
from dataclasses import dataclass

@dataclass
class Action:
    type: str  # react, message, reply, silent
    emoji: str | None = None
    content: str | None = None

def parse_response(text: str) -> list[Action]:
    """
    Parse agent response into actions.
    
    Returns list of Action objects. If no JSON found,
    returns a single reply action with the full text.
    """
    if not text:
        return []
    
    text = text.strip()
    
    # Try to extract JSON (might be wrapped in markdown code block)
    json_match = re.search(r'```json?\s*(.*?)\s*```', text, re.DOTALL)
    if json_match:
        json_str = json_match.group(1)
    elif text.startswith('{'):
        json_str = text
    else:
        # Plain text - treat as reply
        return [Action(type="reply", content=text)]
    
    try:
        data = json.loads(json_str)
        actions = []
        for action_data in data.get("actions", []):
            actions.append(Action(
                type=action_data.get("type", "message"),
                emoji=action_data.get("emoji"),
                content=action_data.get("content"),
            ))
        return actions if actions else [Action(type="silent")]
    except json.JSONDecodeError:
        # Failed to parse - treat as plain text
        return [Action(type="reply", content=text)]
```

### 2. Action Executor (in `discord_bot.py`)

```python
async def execute_actions(
    self,
    actions: list[Action],
    channel: discord.TextChannel,
    message: discord.Message | None = None,
) -> None:
    """Execute a list of actions in order."""
    for action in actions:
        if action.type == "react" and message and action.emoji:
            await message.add_reaction(action.emoji)
        elif action.type == "message" and action.content:
            await channel.send(action.content)
        elif action.type == "reply" and message and action.content:
            await message.reply(action.content)
        elif action.type == "silent":
            pass  # Explicit no-op
```

### 3. Integration

Modify `on_message` to use the parser:

```python
# After getting final_text from _process_response
actions = parse_response(final_text)
await self.execute_actions(actions, channel, message)
```

## Agent Instructions

Add to agent persona/instructions:

> When you want fine control over Discord output, you can return JSON:
> ```json
> {"actions": [{"type": "react", "emoji": "👀"}, {"type": "reply", "content": "Done!"}]}
> ```
> This lets you react before replying, send multiple messages, or stay silent.
> For simple responses, plain text still works.

## Benefits

- ✅ Backwards compatible (plain text still works)
- ✅ Agent controls timing of reactions
- ✅ Can do multiple actions in sequence
- ✅ Explicit silent option
- ✅ Clean separation of concerns

## Future Extensions

- `typing` action to show typing indicator
- `edit` action to edit previous message
- `delete` action to remove a message
- `dm` action to send direct message
