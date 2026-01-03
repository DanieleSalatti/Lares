"""Tests for provider implementations."""

from unittest.mock import AsyncMock

import pytest

from lares.providers.anthropic import AnthropicLLMProvider


class TestAnthropicLLMProvider:
    """Tests for AnthropicLLMProvider."""

    def test_initialization_default_model(self):
        """Provider initializes with default model."""
        provider = AnthropicLLMProvider()
        assert "claude" in provider.model.lower()

    def test_initialization_custom_model(self):
        """Provider accepts custom model."""
        provider = AnthropicLLMProvider(model="claude-3-haiku-20240307")
        assert provider.model == "claude-3-haiku-20240307"

    def test_convert_messages_user(self):
        """Converts user messages."""
        provider = AnthropicLLMProvider()
        result = provider._convert_messages([
            {"role": "user", "content": "Hello"}
        ])
        assert result == [{"role": "user", "content": "Hello"}]

    def test_convert_messages_with_tool_calls(self):
        """Converts assistant messages with tool calls."""
        provider = AnthropicLLMProvider()
        result = provider._convert_messages([
            {
                "role": "assistant",
                "content": "Let me check",
                "tool_calls": [{"id": "1", "name": "read_file", "arguments": {"path": "/test"}}]
            }
        ])
        assert len(result) == 1
        assert result[0]["role"] == "assistant"
        assert isinstance(result[0]["content"], list)
        assert result[0]["content"][0]["type"] == "text"
        assert result[0]["content"][1]["type"] == "tool_use"

    def test_convert_messages_tool_result(self):
        """Converts tool result messages."""
        provider = AnthropicLLMProvider()
        result = provider._convert_messages([
            {"role": "tool", "tool_call_id": "1", "content": "file contents"}
        ])
        assert result[0]["role"] == "user"
        assert result[0]["content"][0]["type"] == "tool_result"

    def test_convert_tools_parameters_format(self):
        """Converts OpenAI/Letta tool format."""
        provider = AnthropicLLMProvider()
        result = provider._convert_tools([{
            "name": "test_tool",
            "description": "A test",
            "parameters": {"type": "object", "properties": {"arg": {"type": "string"}}}
        }])
        assert len(result) == 1
        assert result[0]["name"] == "test_tool"
        assert "input_schema" in result[0]

    def test_convert_tools_already_anthropic(self):
        """Passes through Anthropic format."""
        provider = AnthropicLLMProvider()
        tool = {
            "name": "test",
            "description": "test",
            "input_schema": {"type": "object"}
        }
        result = provider._convert_tools([tool])
        assert result[0] == tool


class TestAsyncToolExecutor:
    """Tests for AsyncToolExecutor."""

    def test_initialization(self):
        """Executor initializes with optional discord and mcp_url."""
        from lares.providers.tool_executor import AsyncToolExecutor
        executor = AsyncToolExecutor()
        assert executor.discord is None
        assert executor.mcp_url is None
        assert executor._current_message_id is None

    def test_set_current_message_id(self):
        """Can set current message ID for reactions."""
        from lares.providers.tool_executor import AsyncToolExecutor
        executor = AsyncToolExecutor()
        executor.set_current_message_id(12345)
        assert executor._current_message_id == 12345

    @pytest.mark.asyncio
    async def test_discord_send_message_no_discord(self):
        """Returns error when Discord not configured."""
        from lares.providers.tool_executor import AsyncToolExecutor
        executor = AsyncToolExecutor()
        result = await executor.execute("discord_send_message", {"content": "test"})
        assert "not available" in result.lower()

    @pytest.mark.asyncio
    async def test_discord_react_no_message_id(self):
        """Returns error when no message to react to."""
        from lares.providers.tool_executor import AsyncToolExecutor
        mock_discord = AsyncMock()
        executor = AsyncToolExecutor(discord=mock_discord)
        result = await executor.execute("discord_react", {"emoji": "👀"})
        assert "no message" in result.lower()

    @pytest.mark.asyncio
    async def test_discord_send_message_with_discord(self):
        """Sends message when Discord is configured."""
        from lares.providers.tool_executor import AsyncToolExecutor
        mock_discord = AsyncMock()
        executor = AsyncToolExecutor(discord=mock_discord)
        result = await executor.execute("discord_send_message", {"content": "Hello!"})
        mock_discord.send_message.assert_called_once_with("Hello!")
        assert "sent" in result.lower()

    @pytest.mark.asyncio
    async def test_discord_react_with_message_id(self):
        """Reacts when Discord and message ID are set."""
        from lares.providers.tool_executor import AsyncToolExecutor
        mock_discord = AsyncMock()
        executor = AsyncToolExecutor(discord=mock_discord)
        executor.set_current_message_id(12345)
        result = await executor.execute("discord_react", {"emoji": "✅"})
        mock_discord.react.assert_called_once_with(12345, "✅")
        assert "reacted" in result.lower()

    @pytest.mark.asyncio
    async def test_safe_tool_execution(self):
        """Executes safe tools locally."""
        from lares.providers.tool_executor import AsyncToolExecutor
        executor = AsyncToolExecutor()
        result = await executor.execute("list_directory", {"path": "/tmp"})
        assert "queued for approval" not in result.lower()

    @pytest.mark.asyncio
    async def test_approval_required_no_mcp(self):
        """Returns error for approval-required tools without MCP."""
        from lares.providers.tool_executor import AsyncToolExecutor
        executor = AsyncToolExecutor()
        result = await executor.execute("run_shell_command", {"command": "echo test"})
        assert "requires approval" in result.lower() or "mcp not configured" in result.lower()


class TestOrchestratorFactory:
    """Tests for orchestrator factory."""

    @pytest.mark.asyncio
    async def test_create_orchestrator_imports(self):
        """Factory function can be imported."""
        from lares.orchestrator_factory import create_orchestrator
        assert callable(create_orchestrator)


class TestOrchestratorIntegration:
    """Integration tests for Orchestrator."""

    def test_orchestrator_config_defaults(self):
        """OrchestratorConfig has sensible defaults."""
        from lares.orchestrator import OrchestratorConfig
        config = OrchestratorConfig()
        assert config.max_tool_iterations == 10

    def test_orchestrator_config_custom(self):
        """OrchestratorConfig accepts custom values."""
        from lares.orchestrator import OrchestratorConfig
        config = OrchestratorConfig(max_tool_iterations=5)
        assert config.max_tool_iterations == 5

    @pytest.mark.asyncio
    async def test_orchestrator_initialization(self):
        """Orchestrator initializes with providers."""
        from lares.orchestrator import Orchestrator, OrchestratorConfig

        mock_llm = AsyncMock()
        mock_memory = AsyncMock()
        mock_tool_executor = AsyncMock()

        orchestrator = Orchestrator(
            llm=mock_llm,
            memory=mock_memory,
            tool_executor=mock_tool_executor,
            config=OrchestratorConfig(),
        )

        assert orchestrator.llm == mock_llm
        assert orchestrator.memory == mock_memory
