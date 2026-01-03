"""Tests for AsyncToolExecutor."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from lares.providers.tool_executor import AsyncToolExecutor


class TestAsyncToolExecutor:
    """Test the AsyncToolExecutor routing logic."""

    @pytest.fixture
    def mock_discord(self):
        """Create mock Discord actions."""
        discord = MagicMock()
        discord.send_message = AsyncMock()
        discord.react = AsyncMock()
        return discord

    @pytest.fixture
    def executor_with_discord(self, mock_discord):
        """Create executor with Discord configured."""
        return AsyncToolExecutor(discord=mock_discord, mcp_url="http://localhost:8001")

    @pytest.fixture
    def executor_no_mcp(self, mock_discord):
        """Create executor without MCP configured."""
        return AsyncToolExecutor(discord=mock_discord, mcp_url=None)

    @pytest.mark.asyncio
    async def test_discord_send_message(self, executor_with_discord, mock_discord):
        """Test discord_send_message routes to Discord."""
        result = await executor_with_discord.execute(
            "discord_send_message", {"content": "Hello!"}
        )
        assert result == "Message sent"
        mock_discord.send_message.assert_called_once_with("Hello!")

    @pytest.mark.asyncio
    async def test_discord_react(self, executor_with_discord, mock_discord):
        """Test discord_react routes to Discord."""
        executor_with_discord.set_current_message_id(12345)
        result = await executor_with_discord.execute(
            "discord_react", {"emoji": "👍"}
        )
        assert result == "Reacted"
        mock_discord.react.assert_called_once_with(12345, "👍")

    @pytest.mark.asyncio
    async def test_discord_react_no_message(self, executor_with_discord, mock_discord):
        """Test discord_react fails gracefully with no message ID."""
        result = await executor_with_discord.execute(
            "discord_react", {"emoji": "👍"}
        )
        assert result == "No message to react to"
        mock_discord.react.assert_not_called()

    @pytest.mark.asyncio
    async def test_tool_routed_to_mcp(self, executor_with_discord):
        """Test non-Discord tools are routed to MCP."""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={"result": "file contents"})

        mock_post = MagicMock()
        mock_post.__aenter__ = AsyncMock(return_value=mock_response)
        mock_post.__aexit__ = AsyncMock()

        mock_session = MagicMock()
        mock_session.post = MagicMock(return_value=mock_post)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock()

        with patch("aiohttp.ClientSession", return_value=mock_session):
            result = await executor_with_discord.execute(
                "read_file", {"path": "/some/file"}
            )
            assert result == "file contents"

    @pytest.mark.asyncio
    async def test_tool_queued_for_approval(self, executor_with_discord):
        """Test tools are queued via MCP /approvals endpoint when needed."""
        mock_response = AsyncMock()
        mock_response.status = 202
        mock_response.json = AsyncMock(return_value={"approval_id": "abc123"})

        mock_session = MagicMock()
        mock_session.post = MagicMock(return_value=AsyncMock(
            __aenter__=AsyncMock(return_value=mock_response),
            __aexit__=AsyncMock()
        ))
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock()

        with patch("aiohttp.ClientSession", return_value=mock_session):
            result = await executor_with_discord.execute(
                "run_command", {"command": "rm -rf /"}
            )
            assert "Queued for approval" in result
            assert "abc123" in result

    @pytest.mark.asyncio
    async def test_tool_no_mcp(self, executor_no_mcp):
        """Test tools error when MCP not configured."""
        result = await executor_no_mcp.execute(
            "run_command", {"command": "ls"}
        )
        assert "MCP not configured" in result

    @pytest.mark.asyncio
    async def test_discord_not_available(self):
        """Test Discord tools handle missing Discord gracefully."""
        executor = AsyncToolExecutor(discord=None, mcp_url=None)
        result = await executor.execute("discord_send_message", {"content": "Hello"})
        assert "Discord not available" in result


class TestToolExecutorApprovalFlow:
    """Test the approval queuing flow."""

    @pytest.mark.asyncio
    async def test_approval_returns_id(self):
        """Test that queued approvals return the approval ID."""
        executor = AsyncToolExecutor(mcp_url="http://localhost:8001")

        mock_response = AsyncMock()
        mock_response.status = 202
        mock_response.json = AsyncMock(return_value={"approval_id": "test-id-123"})

        mock_post = MagicMock()
        mock_post.__aenter__ = AsyncMock(return_value=mock_response)
        mock_post.__aexit__ = AsyncMock()

        mock_session = MagicMock()
        mock_session.post = MagicMock(return_value=mock_post)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock()

        with patch("aiohttp.ClientSession", return_value=mock_session):
            result = await executor.execute("write_file", {"path": "/x", "content": "y"})

            mock_session.post.assert_called_once_with(
                "http://localhost:8001/approvals",
                json={"tool": "write_file", "args": {"path": "/x", "content": "y"}}
            )

            assert "test-id-123" in result

    @pytest.mark.asyncio
    async def test_approval_immediate_execution(self):
        """Test that 200 response means immediate execution (safe tool)."""
        executor = AsyncToolExecutor(mcp_url="http://localhost:8001")

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={"result": "Success!"})

        mock_post = MagicMock()
        mock_post.__aenter__ = AsyncMock(return_value=mock_response)
        mock_post.__aexit__ = AsyncMock()

        mock_session = MagicMock()
        mock_session.post = MagicMock(return_value=mock_post)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock()

        with patch("aiohttp.ClientSession", return_value=mock_session):
            result = await executor.execute("some_tool", {})
            assert result == "Success!"

    @pytest.mark.asyncio
    async def test_approval_error_handling(self):
        """Test error response from approval endpoint."""
        executor = AsyncToolExecutor(mcp_url="http://localhost:8001")

        mock_response = AsyncMock()
        mock_response.status = 500
        mock_response.json = AsyncMock(return_value={"error": "Internal error"})

        mock_post = MagicMock()
        mock_post.__aenter__ = AsyncMock(return_value=mock_response)
        mock_post.__aexit__ = AsyncMock()

        mock_session = MagicMock()
        mock_session.post = MagicMock(return_value=mock_post)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock()

        with patch("aiohttp.ClientSession", return_value=mock_session):
            result = await executor.execute("some_tool", {})
            assert "MCP error" in result or "Internal error" in result
