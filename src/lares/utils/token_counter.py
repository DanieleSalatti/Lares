"""Token counting utilities using tiktoken."""

import tiktoken

_tokenizer = None


def get_tokenizer(model: str = "claude-3-5-sonnet") -> tiktoken.Encoding:
    """Get tokenizer for a given model.

    Claude doesn't have tiktoken support, so we use cl100k_base (GPT-4) as approximation.
    This is reasonably accurate for general text.
    """
    global _tokenizer
    if _tokenizer is None:
        # Use cl100k_base encoding (GPT-4) as approximation for Claude
        _tokenizer = tiktoken.get_encoding("cl100k_base")
    return _tokenizer


def count_tokens(text: str, model: str = "claude-3-5-sonnet") -> int:
    """Count tokens in text."""
    tokenizer = get_tokenizer(model)
    return len(tokenizer.encode(text))


def count_message_tokens(messages: list[dict], model: str = "claude-3-5-sonnet") -> int:
    """Count tokens in a list of messages.

    Approximates the token count for the conversation context.
    """
    total = 0
    for message in messages:
        # Count role
        total += 4  # Approximate overhead per message

        # Count content
        content = message.get("content", "")
        if isinstance(content, str):
            total += count_tokens(content, model)
        elif isinstance(content, list):
            # Handle multi-part content (images, tools, etc.)
            for part in content:
                if isinstance(part, dict) and "text" in part:
                    total += count_tokens(part["text"], model)
                elif isinstance(part, str):
                    total += count_tokens(part, model)
                else:
                    # Tool calls, images, etc. - rough estimate
                    total += 50

        # Count tool calls
        if "tool_calls" in message:
            for tool_call in message["tool_calls"]:
                total += count_tokens(str(tool_call), model)

    return total


def estimate_system_tokens(system_prompt: str, model: str = "claude-3-5-sonnet") -> int:
    """Estimate tokens for system prompt."""
    return count_tokens(system_prompt, model)
