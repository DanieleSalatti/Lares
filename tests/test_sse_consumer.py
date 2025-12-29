"""Tests for SSE event consumer."""

import pytest
from lares.sse_consumer import (
    DiscordMessageEvent,
    DiscordReactionEvent,
    SSEConsumer,
)


class TestDiscordEvents:
    """Test event dataclasses."""

    def test_message_event_creation(self):
        event = DiscordMessageEvent(
            message_id=123,
            channel_id=456,
            author_id=789,
            author_name="TestUser",
            content="Hello world",
            timestamp="2025-12-27T23:00:00Z",
        )
        assert event.message_id == 123
        assert event.author_name == "TestUser"
        assert event.content == "Hello world"

    def test_reaction_event_creation(self):
        event = DiscordReactionEvent(
            message_id=123,
            channel_id=456,
            user_id=789,
            emoji="👍",
        )
        assert event.message_id == 123
        assert event.emoji == "👍"


class TestSSEConsumer:
    """Test SSE consumer."""

    def test_consumer_initialization(self):
        consumer = SSEConsumer()
        assert consumer.mcp_url == "http://localhost:8765"
        assert consumer._message_handlers == []
        assert consumer._reaction_handlers == []
        assert consumer._running is False

    def test_consumer_custom_url(self):
        consumer = SSEConsumer("http://custom:9000")
        assert consumer.mcp_url == "http://custom:9000"

    def test_register_message_handler(self):
        consumer = SSEConsumer()

        async def handler(event):
            pass

        consumer.on_message(handler)
        assert len(consumer._message_handlers) == 1
        assert consumer._message_handlers[0] is handler

    def test_register_reaction_handler(self):
        consumer = SSEConsumer()

        async def handler(event):
            pass

        consumer.on_reaction(handler)
        assert len(consumer._reaction_handlers) == 1

    def test_stop_sets_running_false(self):
        consumer = SSEConsumer()
        consumer._running = True
        consumer.stop()
        assert consumer._running is False


class TestEventDispatch:
    """Test event dispatch logic."""

    @pytest.mark.asyncio
    async def test_dispatch_message_event(self):
        consumer = SSEConsumer()
        received = []

        async def handler(event):
            received.append(event)

        consumer.on_message(handler)

        event = {
            "event": "discord_message",
            "data": {
                "message_id": 1,
                "channel_id": 2,
                "author_id": 3,
                "author_name": "Test",
                "content": "Hello",
                "timestamp": "2025-01-01T00:00:00Z",
            },
        }
        await consumer._dispatch_event(event)

        assert len(received) == 1
        assert received[0].content == "Hello"
        assert received[0].author_name == "Test"

    @pytest.mark.asyncio
    async def test_dispatch_reaction_event(self):
        consumer = SSEConsumer()
        received = []

        async def handler(event):
            received.append(event)

        consumer.on_reaction(handler)

        event = {
            "event": "discord_reaction",
            "data": {
                "message_id": 1,
                "channel_id": 2,
                "user_id": 3,
                "emoji": "✅",
            },
        }
        await consumer._dispatch_event(event)

        assert len(received) == 1
        assert received[0].emoji == "✅"

    @pytest.mark.asyncio
    async def test_dispatch_ignores_unknown_events(self):
        consumer = SSEConsumer()
        received = []

        async def handler(event):
            received.append(event)

        consumer.on_message(handler)

        event = {"event": "unknown_type", "data": {"foo": "bar"}}
        await consumer._dispatch_event(event)

        assert len(received) == 0

    @pytest.mark.asyncio
    async def test_handler_error_does_not_crash(self):
        consumer = SSEConsumer()

        async def bad_handler(event):
            raise ValueError("Handler error")

        consumer.on_message(bad_handler)

        event = {
            "event": "discord_message",
            "data": {
                "message_id": 1,
                "channel_id": 2,
                "author_id": 3,
                "author_name": "Test",
                "content": "Hello",
                "timestamp": "2025-01-01T00:00:00Z",
            },
        }
        # Should not raise
        await consumer._dispatch_event(event)


class TestDiscordClient:
    """Tests for the DiscordClient HTTP wrapper."""

    def test_client_initialization(self):
        from lares.sse_consumer import DiscordClient

        client = DiscordClient()
        assert client.mcp_url == "http://localhost:8765"

    def test_client_custom_url(self):
        from lares.sse_consumer import DiscordClient

        client = DiscordClient(mcp_url="http://custom:9000")
        assert client.mcp_url == "http://custom:9000"

    @pytest.mark.asyncio
    async def test_send_message_builds_payload(self):
        from lares.sse_consumer import DiscordClient
        from unittest.mock import AsyncMock, patch, MagicMock

        client = DiscordClient()

        # Mock the aiohttp session
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={"status": "ok", "message_id": "123"})

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        mock_session.post = MagicMock(return_value=MagicMock(
            __aenter__=AsyncMock(return_value=mock_response),
            __aexit__=AsyncMock(return_value=None)
        ))

        with patch("aiohttp.ClientSession", return_value=mock_session):
            result = await client.send_message("Hello!")

        assert result == {"status": "ok", "message_id": "123"}
        mock_session.post.assert_called_once_with(
            "http://localhost:8765/discord/send",
            json={"content": "Hello!"}
        )

    @pytest.mark.asyncio
    async def test_send_message_with_reply(self):
        from lares.sse_consumer import DiscordClient
        from unittest.mock import AsyncMock, patch, MagicMock

        client = DiscordClient()

        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={"status": "ok", "message_id": "456"})

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        mock_session.post = MagicMock(return_value=MagicMock(
            __aenter__=AsyncMock(return_value=mock_response),
            __aexit__=AsyncMock(return_value=None)
        ))

        with patch("aiohttp.ClientSession", return_value=mock_session):
            result = await client.send_message("Reply!", reply_to=123)

        mock_session.post.assert_called_once_with(
            "http://localhost:8765/discord/send",
            json={"content": "Reply!", "reply_to": "123"}
        )

    @pytest.mark.asyncio
    async def test_react_builds_payload(self):
        from lares.sse_consumer import DiscordClient
        from unittest.mock import AsyncMock, patch, MagicMock

        client = DiscordClient()

        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={"status": "ok", "emoji": "👀"})

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        mock_session.post = MagicMock(return_value=MagicMock(
            __aenter__=AsyncMock(return_value=mock_response),
            __aexit__=AsyncMock(return_value=None)
        ))

        with patch("aiohttp.ClientSession", return_value=mock_session):
            result = await client.react(12345, "✅")

        assert result == {"status": "ok", "emoji": "👀"}
        mock_session.post.assert_called_once_with(
            "http://localhost:8765/discord/react",
            json={"message_id": "12345", "emoji": "✅"}
        )
