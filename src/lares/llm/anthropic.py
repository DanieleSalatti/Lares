"""Anthropic (Claude) LLM provider."""

import anthropic
import structlog

from .provider import LLMProvider, LLMResponse, ToolCall

log = structlog.get_logger()


class AnthropicProvider(LLMProvider):
    """LLM provider for Anthropic's Claude models."""

    def __init__(self, api_key: str, model: str = "claude-opus-4-5-20251101"):
        self.client = anthropic.Anthropic(api_key=api_key)
        self.async_client = anthropic.AsyncAnthropic(api_key=api_key)
        self.model = model

    @property
    def model_name(self) -> str:
        return self.model

    def send(self, messages: list[dict], system_prompt: str | None = None,
             tools: list[dict] | None = None, max_tokens: int = 4096) -> LLMResponse:
        kwargs = {"model": self.model, "max_tokens": max_tokens, "messages": messages}
        if system_prompt:
            kwargs["system"] = system_prompt
        if tools:
            kwargs["tools"] = tools

        log.debug("anthropic_send", model=self.model, message_count=len(messages))
        response = self.client.messages.create(**kwargs)
        return self._parse_response(response)

    async def send_async(self, messages: list[dict], system_prompt: str | None = None,
                         tools: list[dict] | None = None, max_tokens: int = 4096) -> LLMResponse:
        kwargs = {"model": self.model, "max_tokens": max_tokens, "messages": messages}
        if system_prompt:
            kwargs["system"] = system_prompt
        if tools:
            kwargs["tools"] = tools

        log.debug("anthropic_send_async", model=self.model, message_count=len(messages))
        response = await self.async_client.messages.create(**kwargs)
        return self._parse_response(response)

    def _parse_response(self, response) -> LLMResponse:
        content = ""
        tool_calls = []

        for block in response.content:
            if block.type == "text":
                content += block.text
            elif block.type == "tool_use":
                tool_calls.append(ToolCall(id=block.id, name=block.name, arguments=block.input))

        return LLMResponse(
            content=content,
            tool_calls=tool_calls,
            usage={"input_tokens": response.usage.input_tokens,
                   "output_tokens": response.usage.output_tokens,
                   "total_tokens": response.usage.input_tokens + response.usage.output_tokens},
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            model=response.model,
            stop_reason=response.stop_reason,
        )
