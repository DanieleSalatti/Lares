"""Anthropic implementation of LLMProvider."""

import os
from typing import Any

import structlog

from .llm import LLMProvider, LLMResponse, ToolCall

log = structlog.get_logger()

_anthropic_client = None


def _get_client():
    """Get or create the async Anthropic client."""
    global _anthropic_client
    if _anthropic_client is None:
        import anthropic

        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY not set")
        _anthropic_client = anthropic.AsyncAnthropic(api_key=api_key)
    return _anthropic_client


class AnthropicLLMProvider(LLMProvider):
    """Async Claude provider for Orchestrator."""

    def __init__(self, model: str = "claude-opus-4-5-20251101"):
        self.model = model
        self._client = None

    async def initialize(self) -> None:
        self._client = _get_client()
        log.info("anthropic_provider_initialized", model=self.model)

    async def shutdown(self) -> None:
        pass

    async def send(
        self,
        messages: list[dict[str, Any]],
        system_prompt: str,
        tools: list[dict[str, Any]] | None = None,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        if not self._client:
            self._client = _get_client()

        anthropic_messages = self._convert_messages(messages)
        anthropic_tools = self._convert_tools(tools) if tools else None

        kwargs: dict[str, Any] = {
            "model": self.model,
            "max_tokens": max_tokens,
            "system": system_prompt,
            "messages": anthropic_messages,
        }
        if anthropic_tools:
            kwargs["tools"] = anthropic_tools

        response = await self._client.messages.create(**kwargs)
        return self._parse_response(response)

    def _convert_messages(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        result = []
        for msg in messages:
            role = msg.get("role", "")
            content = msg.get("content", "")
            if role == "user":
                result.append({"role": "user", "content": content})
            elif role == "assistant":
                tool_calls = msg.get("tool_calls", [])
                if tool_calls:
                    blocks = []
                    if content:
                        blocks.append({"type": "text", "text": content})
                    for tc in tool_calls:
                        blocks.append({
                            "type": "tool_use",
                            "id": tc["id"],
                            "name": tc["name"],
                            "input": tc.get("arguments", {}),
                        })
                    result.append({"role": "assistant", "content": blocks})
                else:
                    result.append({"role": "assistant", "content": content})
            elif role == "tool":
                result.append({
                    "role": "user",
                    "content": [{
                        "type": "tool_result",
                        "tool_use_id": msg.get("tool_call_id", ""),
                        "content": content,
                    }],
                })
        return result

    def _convert_tools(self, tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
        result = []
        for tool in tools:
            if "input_schema" in tool:
                result.append(tool)
            elif "parameters" in tool:
                result.append({
                    "name": tool.get("name", ""),
                    "description": tool.get("description", ""),
                    "input_schema": tool.get("parameters", {"type": "object"}),
                })
        return result

    def _parse_response(self, response) -> LLMResponse:
        content = ""
        tool_calls = []
        for block in response.content:
            if block.type == "text":
                content += block.text
            elif block.type == "tool_use":
                tool_calls.append(ToolCall(id=block.id, name=block.name, arguments=block.input))
        usage = {}
        if response.usage:
            usage = {
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
                "total_tokens": response.usage.input_tokens + response.usage.output_tokens,
            }
        return LLMResponse(
            content=content,
            tool_calls=tool_calls,
            stop_reason=response.stop_reason,
            usage=usage,
        )
