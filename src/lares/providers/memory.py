"""Memory provider interface.

Abstracts memory storage backends like Letta, Hindsight, etc.
"""

from abc import abstractmethod
from dataclasses import dataclass, field
from typing import Any

from .base import Provider


@dataclass
class MemoryBlock:
    """A block of memory content."""
    label: str
    value: str
    description: str = ""


@dataclass
class MemoryContext:
    """Context retrieved from memory for LLM consumption."""
    # System-level context
    base_instructions: str = ""

    # Memory blocks (persona, human, state, etc.)
    blocks: list[MemoryBlock] = field(default_factory=list)

    # Conversation history
    messages: list[dict[str, Any]] = field(default_factory=list)

    # Available tools
    tools: list[dict[str, Any]] = field(default_factory=list)

    # Metadata
    total_tokens: int = 0


class MemoryProvider(Provider):
    """Interface for memory storage backends."""

    @abstractmethod
    async def get_context(self) -> MemoryContext:
        """Retrieve full context for LLM prompt building."""
        pass

    @abstractmethod
    async def add_message(self, role: str, content: str) -> None:
        """Add a message to conversation history."""
        pass

    @abstractmethod
    async def update_block(self, label: str, value: str) -> None:
        """Update a memory block's value."""
        pass

    @abstractmethod
    async def search(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        """Search memory for relevant content."""
        pass
