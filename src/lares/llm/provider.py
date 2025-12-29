"""Base LLM provider interface."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class LLMResponse:
    """Response from an LLM call."""

    content: str
    # Tool calls the LLM wants to make
    tool_calls: list[dict] = field(default_factory=list)
    # Usage stats (optional)
    input_tokens: int | None = None
    output_tokens: int | None = None
    # Model used
    model: str | None = None
    # Stop reason
    stop_reason: str | None = None


class LLMProvider(ABC):
    """Abstract base class for LLM providers.

    Implementations must provide a way to send messages
    and receive responses from an LLM.
    """

    @abstractmethod
    def send(
        self,
        messages: list[dict],
        system_prompt: str | None = None,
        tools: list[dict] | None = None,
    ) -> LLMResponse:
        """Send messages to the LLM and get a response.

        Args:
            messages: List of message dicts with 'role' and 'content'
            system_prompt: Optional system prompt to prepend
            tools: Optional list of tool definitions for function calling

        Returns:
            LLMResponse with content and optional tool calls
        """
        ...

    @abstractmethod
    async def send_async(
        self,
        messages: list[dict],
        system_prompt: str | None = None,
        tools: list[dict] | None = None,
    ) -> LLMResponse:
        """Async version of send."""
        ...

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Return the model name/identifier."""
        ...
