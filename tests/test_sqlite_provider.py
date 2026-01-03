"""Tests for SqliteMemoryProvider."""

import os
import tempfile

import pytest

from lares.providers import SqliteMemoryProvider


@pytest.fixture
async def provider():
    """Create a test provider with temp database."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        p = SqliteMemoryProvider(db_path=db_path, base_instructions="Test system prompt")
        await p.initialize()
        yield p
        await p.shutdown()


@pytest.mark.asyncio
async def test_initialize_creates_tables(provider):
    """Test that initialization creates required tables."""
    # Tables should exist after init
    cursor = await provider._db.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    )
    tables = [row[0] for row in await cursor.fetchall()]

    assert "messages" in tables
    assert "memory_blocks" in tables
    assert "summaries" in tables


@pytest.mark.asyncio
async def test_add_and_get_message(provider):
    """Test adding and retrieving messages."""
    msg_id = await provider.add_message("user", "Hello, world!")
    assert msg_id is not None

    context = await provider.get_context()
    assert len(context.messages) == 1
    assert context.messages[0]["role"] == "user"
    assert context.messages[0]["content"] == "Hello, world!"


@pytest.mark.asyncio
async def test_add_message_with_tool_calls(provider):
    """Test adding assistant message with tool calls."""
    tool_calls = [{"id": "call_123", "name": "test_tool", "arguments": "{}"}]
    await provider.add_message("assistant", "Calling tool...", tool_calls=tool_calls)

    context = await provider.get_context()
    assert len(context.messages) == 1
    assert context.messages[0]["tool_calls"] == tool_calls


@pytest.mark.asyncio
async def test_update_block(provider):
    """Test updating memory blocks (upsert)."""
    await provider.update_block("persona", "I am a test assistant")

    context = await provider.get_context()
    assert len(context.blocks) == 1
    assert context.blocks[0].label == "persona"
    assert context.blocks[0].value == "I am a test assistant"

    # Update existing block
    await provider.update_block("persona", "I am an updated assistant")

    context = await provider.get_context()
    assert len(context.blocks) == 1
    assert context.blocks[0].value == "I am an updated assistant"


@pytest.mark.asyncio
async def test_search_messages(provider):
    """Test basic text search."""
    await provider.add_message("user", "Hello Python world!")
    await provider.add_message("user", "Hello JavaScript world!")
    await provider.add_message("user", "Goodbye everyone!")

    results = await provider.search("Python")
    assert len(results) == 1
    assert "Python" in results[0]["content"]

    results = await provider.search("Hello")
    assert len(results) == 2


@pytest.mark.asyncio
async def test_add_summary(provider):
    """Test adding summaries."""
    summary_id = await provider.add_summary(
        "This is a summary of earlier conversations.",
        start_message_id="msg-001",
        end_message_id="msg-100",
    )
    assert summary_id is not None


@pytest.mark.asyncio
async def test_get_message_count(provider):
    """Test message counting."""
    assert await provider.get_message_count() == 0

    await provider.add_message("user", "Message 1")
    await provider.add_message("assistant", "Response 1")

    assert await provider.get_message_count() == 2


@pytest.mark.asyncio
async def test_context_includes_base_instructions(provider):
    """Test that context includes base instructions."""
    context = await provider.get_context()
    assert context.base_instructions == "Test system prompt"


@pytest.mark.asyncio
async def test_messages_ordered_chronologically(provider):
    """Test that messages are returned oldest first."""
    await provider.add_message("user", "First")
    await provider.add_message("assistant", "Second")
    await provider.add_message("user", "Third")

    context = await provider.get_context()
    assert context.messages[0]["content"] == "First"
    assert context.messages[1]["content"] == "Second"
    assert context.messages[2]["content"] == "Third"


@pytest.mark.asyncio
async def test_token_estimation_in_context(tmp_path):
    """Test that get_context estimates tokens."""
    db_path = tmp_path / "test.db"
    provider = SqliteMemoryProvider(
        db_path=str(db_path),
        base_instructions="This is a test system prompt with some content.",
    )
    await provider.initialize()

    # Add some content
    await provider.add_message("user", "Hello, this is a test message!")
    await provider.update_block("test", "Some block content here")

    context = await provider.get_context()

    # Token count should be > 0 now
    assert context.total_tokens > 0
    # Rough check: ~20 words = ~25-30 tokens, so > 10 at minimum
    assert context.total_tokens > 10

    await provider.shutdown()


def test_estimate_tokens():
    """Test the estimate_tokens helper function."""
    from lares.providers.sqlite import estimate_tokens

    # Empty string = 0 tokens
    assert estimate_tokens("") == 0
    assert estimate_tokens(None) == 0  # type: ignore

    # 4 chars = 1 token
    assert estimate_tokens("test") == 1

    # 8 chars = 2 tokens
    assert estimate_tokens("testtest") == 2

    # Longer text
    text = "This is a longer piece of text to estimate tokens"
    assert estimate_tokens(text) == len(text) // 4
