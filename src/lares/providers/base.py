"""Base provider interface."""

from abc import ABC, abstractmethod


class Provider(ABC):
    """Base class for all providers."""

    @abstractmethod
    async def initialize(self) -> None:
        """Initialize the provider. Called once at startup."""
        pass

    @abstractmethod
    async def shutdown(self) -> None:
        """Shutdown the provider. Called on exit."""
        pass
