"""OpenAI implementation of LLMProvider."""

import json
import os
from typing import Any

import structlog

from .llm import LLMProvider, LLMResponse, ToolCall

log = structlog.get_logger()

_openai_client = None


def _get_client() -> Any:
    """Get or create the async OpenAI client."""
    global _openai_client
    if _openai_client is None:
        import openai

        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY not set")
        _openai_client = openai.AsyncOpenAI(api_key=api_key)
    return _openai_client


class OpenAILLMProvider(LLMProvider):
    """Async OpenAI provider for Orchestrator."""

    def __init__(self, model: str = "gpt-4o"):
        self.model = model
        self._client = None

    async def initialize(self) -> None:
        self._client = _get_client()
        log.info("openai_provider_initialized", model=self.model)

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

        openai_messages = self._convert_messages(messages, system_prompt)
        openai_tools = self._convert_tools(tools) if tools else None

        kwargs: dict[str, Any] = {
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": openai_messages,
        }
        if openai_tools:
            kwargs["tools"] = openai_tools

        response = await self._client.chat.completions.create(**kwargs)
        return self._parse_response(response)

    def _convert_messages(
        self, messages: list[dict[str, Any]], system_prompt: str
    ) -> list[dict[str, Any]]:
        result = [{"role": "system", "content": system_prompt}]

        for msg in messages:
            role = msg.get("role", "")
            content = msg.get("content", "")

            if role == "user":
                result.append({"role": "user", "content": content})
            elif role == "assistant":
                tool_calls = msg.get("tool_calls", [])
                if tool_calls:
                    openai_tool_calls = []
                    for tc in tool_calls:
                        openai_tool_calls.append({
                            "id": tc["id"],
                            "type": "function",
                            "function": {
                                "name": tc["name"],
                                "arguments": json.dumps(tc.get("arguments", {})),
                            },
                        })
                    result.append({
                        "role": "assistant",
                        "content": content or None,
                        "tool_calls": openai_tool_calls,
                    })
                else:
                    result.append({"role": "assistant", "content": content})
            elif role == "tool":
                result.append({
                    "role": "tool",
                    "tool_call_id": msg.get("tool_call_id", ""),
                    "content": content,
                })
        return result

    def _convert_tools(self, tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
        result = []
        for tool in tools:
            name = tool.get("name", "")
            description = tool.get("description", "")
            if "input_schema" in tool:
                parameters = tool["input_schema"]
            elif "parameters" in tool:
                parameters = tool["parameters"]
            else:
                parameters = {"type": "object", "properties": {}}

            result.append({
                "type": "function",
                "function": {
                    "name": name,
                    "description": description,
                    "parameters": parameters,
                },
            })
        return result

    def _parse_response(self, response: Any) -> LLMResponse:
        message = response.choices[0].message
        content = message.content or ""
        tool_calls = []

        if message.tool_calls:
            for tc in message.tool_calls:
                try:
                    arguments = json.loads(tc.function.arguments)
                except json.JSONDecodeError:
                    arguments = {}
                tool_calls.append(
                    ToolCall(id=tc.id, name=tc.function.name, arguments=arguments)
                )

        usage = {}
        if response.usage:
            usage = {
                "input_tokens": response.usage.prompt_tokens,
                "output_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens,
            }

        return LLMResponse(
            content=content,
            tool_calls=tool_calls,
            stop_reason=response.choices[0].finish_reason,
            usage=usage,
        )
