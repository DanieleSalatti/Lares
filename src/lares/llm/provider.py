"""Base LLM provider interface."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolCall:
    """A tool call requested by the LLM."""
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class LLMResponse:
    """Response from an LLM call."""
    content: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    usage: dict[str, int] | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    model: str | None = None
    stop_reason: str | None = None


class LLMProvider(ABC):
    """Abstract base class for LLM providers."""

    @abstractmethod
    def send(self, messages: list[dict], system_prompt: str | None = None,
             tools: list[dict] | None = None, max_tokens: int = 4096) -> LLMResponse:
        ...

    @abstractmethod
    async def send_async(self, messages: list[dict], system_prompt: str | None = None,
                         tools: list[dict] | None = None, max_tokens: int = 4096) -> LLMResponse:
        ...

    @property
    @abstractmethod
    def model_name(self) -> str:
        ...
