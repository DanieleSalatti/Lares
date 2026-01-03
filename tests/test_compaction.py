"""Tests for compaction service."""

import os
import tempfile
from unittest.mock import AsyncMock

import pytest

from lares.compaction import (
    CompactionService,
    ensure_context_headroom,
    estimate_context_tokens,
    estimate_tokens,
)
from lares.providers import MemoryBlock, SqliteMemoryProvider
from lares.providers.llm import LLMResponse


@pytest.fixture
async def memory_provider():
    """Create a test memory provider."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        provider = SqliteMemoryProvider(db_path=db_path, base_instructions="Test")
        await provider.initialize()
        yield provider
        await provider.shutdown()


@pytest.fixture
def mock_llm():
    """Create a mock LLM provider."""
    llm = AsyncMock()
    llm.complete = AsyncMock(return_value=LLMResponse(
        content="Summary: User discussed various topics.",
        tool_calls=[],
        stop_reason="end_turn",
    ))
    return llm


class TestEstimateTokens:
    def test_empty_string(self):
        assert estimate_tokens("") == 0

    def test_short_string(self):
        assert estimate_tokens("Hello World!") == 3

    def test_longer_string(self):
        text = "a" * 100
        assert estimate_tokens(text) == 25


class TestEstimateContextTokens:
    def test_empty_context(self):
        tokens = estimate_context_tokens("", [], [], [])
        assert tokens == 0

    def test_with_instructions(self):
        tokens = estimate_context_tokens("x" * 400, [], [], [])
        assert tokens == 100

    def test_with_blocks(self):
        blocks = [MemoryBlock(label="test", value="x" * 100, description="desc")]
        tokens = estimate_context_tokens("", blocks, [], [])
        assert tokens == 27


class TestCompactionService:
    @pytest.mark.asyncio
    async def test_needs_compaction_false_when_empty(self, memory_provider, mock_llm):
        service = CompactionService(memory_provider, mock_llm, context_limit=1000)
        assert await service.needs_compaction() is False

    @pytest.mark.asyncio
    async def test_needs_compaction_true_when_over_threshold(self, memory_provider, mock_llm):
        for i in range(30):
            await memory_provider.add_message("user", "x" * 100)
        service = CompactionService(memory_provider, mock_llm, context_limit=1000)
        assert await service.needs_compaction() is True

    @pytest.mark.asyncio
    async def test_compact_skips_when_few_messages(self, memory_provider, mock_llm):
        for i in range(5):
            await memory_provider.add_message("user", f"Message {i}")
        service = CompactionService(memory_provider, mock_llm, context_limit=1000)
        result = await service.compact()
        assert result["skipped"] is True

    @pytest.mark.asyncio
    async def test_compact_summarizes_old_messages(self, memory_provider, mock_llm):
        for i in range(50):
            await memory_provider.add_message("user", f"Message {i} content")
        service = CompactionService(memory_provider, mock_llm, context_limit=500, target_ratio=0.20)
        result = await service.compact()
        assert result["skipped"] is False
        assert mock_llm.complete.called


class TestEnsureContextHeadroom:
    @pytest.mark.asyncio
    async def test_no_compaction_when_not_needed(self, memory_provider, mock_llm):
        result = await ensure_context_headroom(memory_provider, mock_llm, context_limit=100000)
        assert result is None
