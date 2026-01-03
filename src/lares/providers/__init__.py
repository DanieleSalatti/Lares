"""Provider interfaces for the modular Lares architecture.

Providers are swappable backends for:
- LLM: Claude, GPT, local models
- Memory: SQLite (default)
- Tools: MCP server
"""

from .anthropic import AnthropicLLMProvider
from .base import Provider
from .llm import LLMProvider, LLMResponse, ToolCall
from .memory import MemoryBlock, MemoryContext, MemoryProvider
from .sqlite import SqliteMemoryProvider

__all__ = [
    "Provider",
    "MemoryProvider",
    "MemoryContext",
    "MemoryBlock",
    "LLMProvider",
    "LLMResponse",
    "ToolCall",
    "AnthropicLLMProvider",
    "SqliteMemoryProvider",
]
