"""LLM abstraction layer for Lares.

This module provides a unified interface for different LLM providers,
allowing easy swapping between Claude, GPT, local models, etc.
"""

from .anthropic import AnthropicProvider
from .provider import LLMProvider, LLMResponse

__all__ = ["LLMProvider", "LLMResponse", "AnthropicProvider"]
