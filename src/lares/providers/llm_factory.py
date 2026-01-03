"""Factory for creating LLM providers based on configuration."""

import os
from typing import Literal

import structlog

from .llm import LLMProvider

log = structlog.get_logger()

LLMProviderType = Literal["anthropic", "openai", "ollama"]


def create_llm_provider(
    provider_type: LLMProviderType | None = None,
    model: str | None = None,
) -> LLMProvider:
    """Create an LLM provider based on configuration.

    Args:
        provider_type: Provider type (anthropic, openai, ollama).
                      Defaults to LLM_PROVIDER env var or 'anthropic'.
        model: Model name. Defaults to provider-specific env var.

    Returns:
        Configured LLM provider instance (not yet initialized).
    """
    provider = provider_type or os.getenv("LLM_PROVIDER", "anthropic").lower()

    if provider == "anthropic":
        from .anthropic import AnthropicLLMProvider

        model_name = model or os.getenv("ANTHROPIC_MODEL", "claude-opus-4-5-20251101")
        log.info("creating_llm_provider", provider="anthropic", model=model_name)
        return AnthropicLLMProvider(model=model_name)

    elif provider == "openai":
        from .openai import OpenAILLMProvider

        model_name = model or os.getenv("OPENAI_MODEL", "gpt-4o")
        log.info("creating_llm_provider", provider="openai", model=model_name)
        return OpenAILLMProvider(model=model_name)

    elif provider == "ollama":
        from .ollama import OllamaLLMProvider

        model_name = model or os.getenv("OLLAMA_MODEL", "llama3.2")
        base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        log.info("creating_llm_provider", provider="ollama", model=model_name, base_url=base_url)
        return OllamaLLMProvider(model=model_name, base_url=base_url)

    else:
        raise ValueError(f"Unknown LLM provider: {provider}. Supported: anthropic, openai, ollama")
