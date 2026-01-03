"""Ollama implementation of LLMProvider."""

import json
import os
from typing import Any

import httpx
import structlog

from .llm import LLMProvider, LLMResponse, ToolCall

log = structlog.get_logger()


class OllamaLLMProvider(LLMProvider):
    """Async Ollama provider for Orchestrator.

    Uses the Ollama OpenAI-compatible API endpoint.
    """

    def __init__(self, model: str = "llama3.2", base_url: str = "http://localhost:11434"):
        self.model = model
        self.base_url = base_url.rstrip("/")
        self._client: httpx.AsyncClient | None = None
        self._timeout = float(os.getenv("OLLAMA_TIMEOUT", "300"))

    async def initialize(self) -> None:
        self._client = httpx.AsyncClient(timeout=self._timeout)
        log.info("ollama_provider_initialized", model=self.model, base_url=self.base_url)

    async def shutdown(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    async def send(
        self,
        messages: list[dict[str, Any]],
        system_prompt: str,
        tools: list[dict[str, Any]] | None = None,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        if not self._client:
            self._client = httpx.AsyncClient(timeout=self._timeout)

        ollama_messages = self._convert_messages(messages, system_prompt)
        ollama_tools = self._convert_tools(tools) if tools else None

        payload: dict[str, Any] = {
            "model": self.model,
            "messages": ollama_messages,
            "stream": False,
            "options": {"num_predict": max_tokens},
        }
        if ollama_tools:
            payload["tools"] = ollama_tools

        url = f"{self.base_url}/api/chat"
        log.debug("ollama_request_starting", url=url, model=self.model)
        response = await self._client.post(url, json=payload)
        log.debug("ollama_request_complete", status=response.status_code)
        response.raise_for_status()

        return self._parse_response(response.json())

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
                    ollama_tool_calls = []
                    for tc in tool_calls:
                        ollama_tool_calls.append({
                            "function": {
                                "name": tc["name"],
                                "arguments": tc.get("arguments", {}),
                            },
                        })
                    result.append({
                        "role": "assistant",
                        "content": content,
                        "tool_calls": ollama_tool_calls,
                    })
                else:
                    result.append({"role": "assistant", "content": content})
            elif role == "tool":
                result.append({
                    "role": "tool",
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

    def _parse_response(self, data: dict[str, Any]) -> LLMResponse:
        message = data.get("message", {})
        content = message.get("content", "")
        tool_calls = []

        if message.get("tool_calls"):
            for i, tc in enumerate(message["tool_calls"]):
                func = tc.get("function", {})
                arguments = func.get("arguments", {})
                if isinstance(arguments, str):
                    try:
                        arguments = json.loads(arguments)
                    except json.JSONDecodeError:
                        arguments = {}
                tool_calls.append(
                    ToolCall(
                        id=f"ollama_{i}",
                        name=func.get("name", ""),
                        arguments=arguments,
                    )
                )

        usage = {}
        if "prompt_eval_count" in data or "eval_count" in data:
            input_tokens = data.get("prompt_eval_count", 0)
            output_tokens = data.get("eval_count", 0)
            usage = {
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": input_tokens + output_tokens,
            }

        return LLMResponse(
            content=content,
            tool_calls=tool_calls,
            stop_reason=data.get("done_reason"),
            usage=usage,
        )
