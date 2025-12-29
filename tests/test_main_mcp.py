"""Tests for MCP-based entry point."""

from unittest.mock import AsyncMock, MagicMock
import pytest
from lares.main_mcp import LaresCore


class TestLaresCoreInit:
    def test_initialization(self):
        config = MagicMock()
        config.tools = MagicMock()
        config.user.timezone = "America/Los_Angeles"
        letta_client = MagicMock()
        discord = MagicMock()
        core = LaresCore(config, letta_client, "agent-123", discord, "http://localhost:8765")
        assert core.config == config
        assert core.agent_id == "agent-123"
        assert core.max_tool_iterations == 100  # From LARES_MAX_TOOL_ITERATIONS env


class TestExecuteTool:
    @pytest.fixture
    def core(self):
        config = MagicMock()
        config.tools = MagicMock()
        letta_client = MagicMock()
        discord = AsyncMock()
        return LaresCore(config, letta_client, "agent-123", discord, "http://localhost:8765")

    @pytest.mark.asyncio
    async def test_routes_discord_send_message(self, core):
        core.discord.send_message.return_value = {"status": "OK"}
        await core._execute_tool("discord_send_message", {"content": "Hello!"})
        core.discord.send_message.assert_called_once_with("Hello!", None)

    @pytest.mark.asyncio
    async def test_discord_react_uses_current_message(self, core):
        core._current_message_id = 67890
        core.discord.react.return_value = {"status": "OK"}
        await core._execute_tool("discord_react", {"emoji": "✅"})
        core.discord.react.assert_called_once_with(67890, "✅")

    @pytest.mark.asyncio
    async def test_discord_react_no_message_returns_error(self, core):
        core._current_message_id = None
        result = await core._execute_tool("discord_react", {"emoji": "👀"})
        assert "Error" in result
        core.discord.react.assert_not_called()

    @pytest.mark.asyncio
    async def test_other_tools_use_executor(self, core):
        core.tool_executor.execute = AsyncMock(return_value="file contents")
        result = await core._execute_tool("read_file", {"path": "/some/file"})
        core.tool_executor.execute.assert_called_once()
        assert result == "file contents"
