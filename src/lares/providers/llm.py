"""LLM provider interface.

Abstracts LLM backends like Claude, GPT, local models.
"""

from abc import abstractmethod
from dataclasses import dataclass, field
from typing import Any

from .base import Provider


@dataclass
class ToolCall:
    """A tool call requested by the LLM."""
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class LLMResponse:
    """Response from an LLM call."""
    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    stop_reason: str | None = None
    usage: dict[str, int] = field(default_factory=dict)

    @property
    def has_tool_calls(self) -> bool:
        return len(self.tool_calls) > 0


class LLMProvider(Provider):
    """Interface for LLM backends."""

    model: str

    @abstractmethod
    async def send(
        self,
        messages: list[dict[str, Any]],
        system_prompt: str,
        tools: list[dict[str, Any]] | None = None,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        """Send messages to the LLM and get a response.

        Args:
            messages: Conversation history in provider's format
            system_prompt: System instructions
            tools: Available tools in provider's format
            max_tokens: Maximum tokens in response

        Returns:
            LLMResponse with content and/or tool calls
        """
        pass

    async def complete(
        self,
        messages: list[dict[str, Any]],
        system: str,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        """Simple completion without tools (used by compaction)."""
        return await self.send(messages, system, tools=None, max_tokens=max_tokens)
