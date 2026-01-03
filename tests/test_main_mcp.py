"""Tests for MCP-based entry point."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from lares.main_mcp import LaresCore


class TestLaresCoreInit:
    def test_initialization(self):
        config = MagicMock()
        config.user.timezone = "America/Los_Angeles"
        discord = MagicMock()
        orchestrator = MagicMock()
        core = LaresCore(config, discord, "http://localhost:8765", orchestrator)
        assert core.config == config
        assert core.mcp_url == "http://localhost:8765"


class TestApprovalManager:
    def test_initialization(self):
        from lares.main_mcp import ApprovalManager
        discord = MagicMock()
        manager = ApprovalManager("http://localhost:8765", discord)
        assert manager.mcp_url == "http://localhost:8765"
        assert manager._pending == {}
        assert manager._posted == set()

    @pytest.mark.asyncio
    async def test_handle_reaction_not_pending(self):
        from lares.main_mcp import ApprovalManager
        discord = MagicMock()
        manager = ApprovalManager("http://localhost:8765", discord)
        result = await manager.handle_reaction(12345, "✅", 1)
        assert result is False

    @pytest.mark.asyncio
    async def test_handle_reaction_unknown_emoji(self):
        from lares.main_mcp import ApprovalManager
        discord = MagicMock()
        manager = ApprovalManager("http://localhost:8765", discord)
        manager._pending[12345] = "approval-123"
        result = await manager.handle_reaction(12345, "🤔", 1)
        assert result is False


class TestLaresCoreMessage:
    @pytest.fixture
    def core(self):
        config = MagicMock()
        config.user.timezone = "America/Los_Angeles"
        discord = AsyncMock()
        orchestrator = AsyncMock()
        return LaresCore(config, discord, "http://localhost:8765", orchestrator)

    @pytest.mark.asyncio
    async def test_dedupes_messages(self, core):
        from lares.sse_consumer import DiscordMessageEvent
        event = DiscordMessageEvent(
            message_id=123,
            channel_id=456,
            author_id=789,
            author_name="test",
            content="Hello",
            timestamp="2026-01-01T00:00:00Z"
        )
        await core.handle_message(event)
        core.orchestrator.process_message.assert_called_once()

        core.orchestrator.reset_mock()
        await core.handle_message(event)
        core.orchestrator.process_message.assert_not_called()
