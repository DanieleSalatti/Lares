"""Tests for LLM provider abstraction."""

from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from lares.llm.anthropic import AnthropicProvider
from lares.llm.provider import LLMResponse, ToolCall
from lares.providers.llm import LLMResponse as NewLLMResponse
from lares.providers.llm import ToolCall as NewToolCall
from lares.providers.llm_factory import create_llm_provider
from lares.providers.ollama import OllamaLLMProvider
from lares.providers.openai import OpenAILLMProvider


class TestLLMResponse:
    """Tests for LLMResponse dataclass."""

    def test_basic_response(self):
        response = LLMResponse(content="Hello!")
        assert response.content == "Hello!"
        assert response.tool_calls == []
        assert response.input_tokens is None

    def test_response_with_tool_calls(self):
        tool_calls = [ToolCall(id="tc_1", name="read_file", arguments={"path": "/test"})]
        response = LLMResponse(content="", tool_calls=tool_calls)
        assert len(response.tool_calls) == 1
        assert response.tool_calls[0].name == "read_file"

    def test_response_with_usage(self):
        response = LLMResponse(
            content="Hi",
            input_tokens=100,
            output_tokens=50,
            model="claude-sonnet-4-20250514",
            stop_reason="end_turn"
        )
        assert response.input_tokens == 100
        assert response.output_tokens == 50


class TestAnthropicProvider:
    """Tests for AnthropicProvider."""

    def test_initialization(self):
        provider = AnthropicProvider(api_key="test-key")
        assert provider.model == "claude-opus-4-5-20251101"
        assert provider.model_name == "claude-opus-4-5-20251101"

    def test_custom_model(self):
        provider = AnthropicProvider(api_key="test-key", model="claude-3-haiku-20240307")
        assert provider.model == "claude-3-haiku-20240307"

    @patch("lares.llm.anthropic.anthropic.Anthropic")
    def test_send_basic(self, mock_anthropic_class):
        mock_client = Mock()
        mock_anthropic_class.return_value = mock_client

        text_block = MagicMock()
        text_block.type = "text"
        text_block.text = "Hello!"

        mock_response = MagicMock()
        mock_response.content = [text_block]
        mock_response.usage.input_tokens = 10
        mock_response.usage.output_tokens = 5
        mock_response.model = "claude-sonnet-4-20250514"
        mock_response.stop_reason = "end_turn"
        mock_client.messages.create.return_value = mock_response

        provider = AnthropicProvider(api_key="test-key")
        response = provider.send(
            messages=[{"role": "user", "content": "Hi"}],
            system_prompt="You are helpful."
        )

        assert response.content == "Hello!"
        assert response.input_tokens == 10

    @patch("lares.llm.anthropic.anthropic.Anthropic")
    def test_send_with_tool_use(self, mock_anthropic_class):
        mock_client = Mock()
        mock_anthropic_class.return_value = mock_client

        text_block = MagicMock()
        text_block.type = "text"
        text_block.text = "Let me check that."

        tool_block = MagicMock()
        tool_block.type = "tool_use"
        tool_block.id = "tc_123"
        tool_block.name = "read_file"
        tool_block.input = {"path": "/test"}

        mock_response = MagicMock()
        mock_response.content = [text_block, tool_block]
        mock_response.usage.input_tokens = 20
        mock_response.usage.output_tokens = 15
        mock_response.model = "claude-sonnet-4-20250514"
        mock_response.stop_reason = "tool_use"
        mock_client.messages.create.return_value = mock_response

        provider = AnthropicProvider(api_key="test-key")
        response = provider.send(messages=[{"role": "user", "content": "Read /test"}])

        assert response.content == "Let me check that."
        assert len(response.tool_calls) == 1
        assert response.tool_calls[0].id == "tc_123"
        assert response.tool_calls[0].name == "read_file"
        assert response.tool_calls[0].arguments == {"path": "/test"}


class TestNewLLMResponse:
    """Tests for new LLMResponse dataclass in providers."""

    def test_basic_response(self):
        response = NewLLMResponse(content="Hello!")
        assert response.content == "Hello!"
        assert response.tool_calls == []
        assert response.usage == {}

    def test_response_with_tool_calls(self):
        tool_calls = [NewToolCall(id="tc_1", name="read_file", arguments={"path": "/test"})]
        response = NewLLMResponse(content="", tool_calls=tool_calls)
        assert len(response.tool_calls) == 1
        assert response.tool_calls[0].name == "read_file"

    def test_has_tool_calls_property(self):
        response = NewLLMResponse(content="No tools")
        assert response.has_tool_calls is False

        response_with_tools = NewLLMResponse(
            content="",
            tool_calls=[NewToolCall(id="1", name="test", arguments={})]
        )
        assert response_with_tools.has_tool_calls is True


class TestOpenAIProvider:
    """Tests for OpenAILLMProvider."""

    def test_initialization(self):
        provider = OpenAILLMProvider()
        assert provider.model == "gpt-4o"

    def test_custom_model(self):
        provider = OpenAILLMProvider(model="gpt-4-turbo")
        assert provider.model == "gpt-4-turbo"

    def test_convert_messages_basic(self):
        provider = OpenAILLMProvider()
        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"},
        ]
        result = provider._convert_messages(messages, "You are helpful.")

        assert result[0] == {"role": "system", "content": "You are helpful."}
        assert result[1] == {"role": "user", "content": "Hello"}
        assert result[2] == {"role": "assistant", "content": "Hi there!"}

    def test_convert_messages_with_tool_calls(self):
        provider = OpenAILLMProvider()
        messages = [
            {"role": "user", "content": "Read /test"},
            {
                "role": "assistant",
                "content": "Let me check.",
                "tool_calls": [{"id": "tc_1", "name": "read_file", "arguments": {"path": "/test"}}]
            },
            {"role": "tool", "tool_call_id": "tc_1", "content": "file contents"},
        ]
        result = provider._convert_messages(messages, "System prompt")

        assert len(result) == 4
        assert result[2]["role"] == "assistant"
        assert result[2]["tool_calls"][0]["function"]["name"] == "read_file"
        assert result[3]["role"] == "tool"
        assert result[3]["tool_call_id"] == "tc_1"

    def test_convert_tools(self):
        provider = OpenAILLMProvider()
        tools = [
            {
                "name": "read_file",
                "description": "Read a file",
                "input_schema": {"type": "object", "properties": {"path": {"type": "string"}}}
            }
        ]
        result = provider._convert_tools(tools)

        assert len(result) == 1
        assert result[0]["type"] == "function"
        assert result[0]["function"]["name"] == "read_file"
        assert result[0]["function"]["description"] == "Read a file"

    def test_convert_tools_with_parameters_key(self):
        provider = OpenAILLMProvider()
        tools = [
            {
                "name": "test_tool",
                "description": "A test",
                "parameters": {"type": "object", "properties": {}}
            }
        ]
        result = provider._convert_tools(tools)
        assert result[0]["function"]["parameters"] == {"type": "object", "properties": {}}

    def test_parse_response_basic(self):
        provider = OpenAILLMProvider()

        mock_message = MagicMock()
        mock_message.content = "Hello!"
        mock_message.tool_calls = None

        mock_choice = MagicMock()
        mock_choice.message = mock_message
        mock_choice.finish_reason = "stop"

        mock_usage = MagicMock()
        mock_usage.prompt_tokens = 10
        mock_usage.completion_tokens = 5
        mock_usage.total_tokens = 15

        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_response.usage = mock_usage

        result = provider._parse_response(mock_response)

        assert result.content == "Hello!"
        assert result.tool_calls == []
        assert result.stop_reason == "stop"
        assert result.usage["input_tokens"] == 10
        assert result.usage["output_tokens"] == 5

    def test_parse_response_with_tool_calls(self):
        provider = OpenAILLMProvider()

        mock_tool_call = MagicMock()
        mock_tool_call.id = "call_123"
        mock_tool_call.function.name = "read_file"
        mock_tool_call.function.arguments = '{"path": "/test"}'

        mock_message = MagicMock()
        mock_message.content = ""
        mock_message.tool_calls = [mock_tool_call]

        mock_choice = MagicMock()
        mock_choice.message = mock_message
        mock_choice.finish_reason = "tool_calls"

        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_response.usage = None

        result = provider._parse_response(mock_response)

        assert len(result.tool_calls) == 1
        assert result.tool_calls[0].id == "call_123"
        assert result.tool_calls[0].name == "read_file"
        assert result.tool_calls[0].arguments == {"path": "/test"}

    @pytest.mark.asyncio
    @patch("lares.providers.openai._get_client")
    async def test_send_basic(self, mock_get_client):
        mock_client = AsyncMock()
        mock_get_client.return_value = mock_client

        mock_message = MagicMock()
        mock_message.content = "Hello!"
        mock_message.tool_calls = None

        mock_choice = MagicMock()
        mock_choice.message = mock_message
        mock_choice.finish_reason = "stop"

        mock_usage = MagicMock()
        mock_usage.prompt_tokens = 10
        mock_usage.completion_tokens = 5
        mock_usage.total_tokens = 15

        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_response.usage = mock_usage

        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        provider = OpenAILLMProvider()
        await provider.initialize()
        response = await provider.send(
            messages=[{"role": "user", "content": "Hi"}],
            system_prompt="You are helpful."
        )

        assert response.content == "Hello!"
        assert response.usage["input_tokens"] == 10


class TestOllamaProvider:
    """Tests for OllamaLLMProvider."""

    def test_initialization(self):
        provider = OllamaLLMProvider()
        assert provider.model == "llama3.2"
        assert provider.base_url == "http://localhost:11434"

    def test_custom_model_and_url(self):
        provider = OllamaLLMProvider(model="mistral", base_url="http://remote:11434/")
        assert provider.model == "mistral"
        assert provider.base_url == "http://remote:11434"

    def test_convert_messages_basic(self):
        provider = OllamaLLMProvider()
        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"},
        ]
        result = provider._convert_messages(messages, "You are helpful.")

        assert result[0] == {"role": "system", "content": "You are helpful."}
        assert result[1] == {"role": "user", "content": "Hello"}
        assert result[2] == {"role": "assistant", "content": "Hi there!"}

    def test_convert_messages_with_tool_calls(self):
        provider = OllamaLLMProvider()
        messages = [
            {"role": "user", "content": "Read /test"},
            {
                "role": "assistant",
                "content": "Let me check.",
                "tool_calls": [{"id": "tc_1", "name": "read_file", "arguments": {"path": "/test"}}]
            },
            {"role": "tool", "content": "file contents"},
        ]
        result = provider._convert_messages(messages, "System prompt")

        assert len(result) == 4
        assert result[2]["role"] == "assistant"
        assert result[2]["tool_calls"][0]["function"]["name"] == "read_file"
        assert result[3]["role"] == "tool"

    def test_convert_tools(self):
        provider = OllamaLLMProvider()
        tools = [
            {
                "name": "read_file",
                "description": "Read a file",
                "input_schema": {"type": "object", "properties": {"path": {"type": "string"}}}
            }
        ]
        result = provider._convert_tools(tools)

        assert len(result) == 1
        assert result[0]["type"] == "function"
        assert result[0]["function"]["name"] == "read_file"

    def test_parse_response_basic(self):
        provider = OllamaLLMProvider()
        data = {
            "message": {"content": "Hello!"},
            "done_reason": "stop",
            "prompt_eval_count": 10,
            "eval_count": 5,
        }

        result = provider._parse_response(data)

        assert result.content == "Hello!"
        assert result.tool_calls == []
        assert result.stop_reason == "stop"
        assert result.usage["input_tokens"] == 10
        assert result.usage["output_tokens"] == 5

    def test_parse_response_with_tool_calls(self):
        provider = OllamaLLMProvider()
        data = {
            "message": {
                "content": "",
                "tool_calls": [
                    {"function": {"name": "read_file", "arguments": {"path": "/test"}}}
                ]
            },
            "done_reason": "tool_calls",
        }

        result = provider._parse_response(data)

        assert len(result.tool_calls) == 1
        assert result.tool_calls[0].id == "ollama_0"
        assert result.tool_calls[0].name == "read_file"
        assert result.tool_calls[0].arguments == {"path": "/test"}

    def test_parse_response_with_string_arguments(self):
        provider = OllamaLLMProvider()
        data = {
            "message": {
                "content": "",
                "tool_calls": [
                    {"function": {"name": "test", "arguments": '{"key": "value"}'}}
                ]
            },
        }

        result = provider._parse_response(data)
        assert result.tool_calls[0].arguments == {"key": "value"}

    @pytest.mark.asyncio
    async def test_send_basic(self):
        provider = OllamaLLMProvider()

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value = mock_client

            mock_response = MagicMock()
            mock_response.json.return_value = {
                "message": {"content": "Hello!"},
                "done_reason": "stop",
                "prompt_eval_count": 10,
                "eval_count": 5,
            }
            mock_response.raise_for_status = MagicMock()
            mock_client.post = AsyncMock(return_value=mock_response)

            await provider.initialize()
            response = await provider.send(
                messages=[{"role": "user", "content": "Hi"}],
                system_prompt="You are helpful."
            )

            assert response.content == "Hello!"
            assert response.usage["input_tokens"] == 10


class TestLLMFactory:
    """Tests for LLM provider factory."""

    def test_default_provider(self):
        with patch.dict("os.environ", {}, clear=True):
            provider = create_llm_provider()
            from lares.providers.anthropic import AnthropicLLMProvider
            assert isinstance(provider, AnthropicLLMProvider)
            assert provider.model == "claude-opus-4-5-20251101"

    def test_anthropic_provider_explicit(self):
        provider = create_llm_provider(provider_type="anthropic")
        from lares.providers.anthropic import AnthropicLLMProvider
        assert isinstance(provider, AnthropicLLMProvider)

    def test_anthropic_custom_model(self):
        provider = create_llm_provider(provider_type="anthropic", model="claude-3-haiku-20240307")
        assert provider.model == "claude-3-haiku-20240307"

    def test_openai_provider(self):
        provider = create_llm_provider(provider_type="openai")
        assert isinstance(provider, OpenAILLMProvider)
        assert provider.model == "gpt-4o"

    def test_openai_custom_model(self):
        provider = create_llm_provider(provider_type="openai", model="gpt-4-turbo")
        assert provider.model == "gpt-4-turbo"

    def test_ollama_provider(self):
        provider = create_llm_provider(provider_type="ollama")
        assert isinstance(provider, OllamaLLMProvider)
        assert provider.model == "llama3.2"

    def test_ollama_custom_model(self):
        provider = create_llm_provider(provider_type="ollama", model="mistral")
        assert provider.model == "mistral"

    def test_env_var_provider_selection(self):
        with patch.dict("os.environ", {"LLM_PROVIDER": "openai"}, clear=False):
            provider = create_llm_provider()
            assert isinstance(provider, OpenAILLMProvider)

    def test_env_var_model_override(self):
        with patch.dict("os.environ", {"ANTHROPIC_MODEL": "claude-3-sonnet-20240229"}, clear=False):
            provider = create_llm_provider(provider_type="anthropic")
            assert provider.model == "claude-3-sonnet-20240229"

    def test_invalid_provider_raises(self):
        with pytest.raises(ValueError, match="Unknown LLM provider"):
            create_llm_provider(provider_type="invalid")
