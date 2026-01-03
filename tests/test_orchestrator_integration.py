"""Integration tests for Orchestrator with SQLite memory provider.

These tests verify the full flow without actually calling the LLM.
"""

import os
import tempfile
from unittest.mock import AsyncMock, MagicMock

import pytest

from lares.orchestrator import Orchestrator, OrchestratorConfig
from lares.providers.sqlite import SqliteMemoryProvider


class MockLLMProvider:
    """Mock LLM that returns canned responses."""

    def __init__(self, responses: list[dict] | None = None):
        self.responses = responses or []
        self.call_count = 0
        self.calls = []

    async def initialize(self):
        pass

    async def shutdown(self):
        pass

    async def send(self, messages, system_prompt, tools=None, max_tokens=4096):
        """Return next canned response."""
        self.calls.append({
            "messages": messages,
            "system_prompt": system_prompt,
            "tools": tools,
        })

        if self.call_count < len(self.responses):
            response = self.responses[self.call_count]
            self.call_count += 1
        else:
            # Default response
            response = {"content": "Default response", "tool_calls": []}

        # Create response object
        result = MagicMock()
        result.content = response.get("content", "")
        result.tool_calls = response.get("tool_calls", [])
        result.has_tool_calls = bool(result.tool_calls)
        result.usage = {"total_tokens": 100}
        return result


class TestOrchestratorWithSQLite:
    """Test Orchestrator with real SQLite provider."""

    @pytest.fixture
    def temp_db(self):
        """Create temporary database."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            yield f.name
        os.unlink(f.name)

    @pytest.fixture
    async def sqlite_provider(self, temp_db):
        """Create and initialize SQLite provider."""
        provider = SqliteMemoryProvider(
            db_path=temp_db,
            base_instructions="You are a helpful assistant.",
        )
        await provider.initialize()

        # Add some memory blocks
        await provider.update_block("persona", "I am Lares, a helpful AI.")
        await provider.update_block("human", "My human is Daniele.")

        yield provider
        await provider.shutdown()

    @pytest.mark.asyncio
    async def test_basic_message_flow(self, sqlite_provider):
        """Test processing a simple message."""
        llm = MockLLMProvider([
            {"content": "Hello! How can I help?", "tool_calls": []}
        ])

        async def mock_tool_executor(name, args):
            return f"Tool {name} executed"

        orchestrator = Orchestrator(
            llm=llm,
            memory=sqlite_provider,
            tool_executor=mock_tool_executor,
        )

        result = await orchestrator.process_message("Hello!")

        assert result.response_text == "Hello! How can I help?"
        assert result.total_iterations == 1
        assert len(result.tool_calls_made) == 0
        assert llm.call_count == 1

    @pytest.mark.asyncio
    async def test_memory_blocks_in_system_prompt(self, sqlite_provider):
        """Test that memory blocks are included in system prompt."""
        llm = MockLLMProvider([
            {"content": "Response", "tool_calls": []}
        ])

        orchestrator = Orchestrator(
            llm=llm,
            memory=sqlite_provider,
            tool_executor=AsyncMock(return_value="ok"),
        )

        await orchestrator.process_message("Test")

        # Check system prompt contains memory blocks
        system_prompt = llm.calls[0]["system_prompt"]
        assert "persona" in system_prompt
        assert "Lares" in system_prompt
        assert "human" in system_prompt
        assert "Daniele" in system_prompt

    @pytest.mark.asyncio
    async def test_messages_persisted(self, sqlite_provider):
        """Test that messages are saved to SQLite."""
        llm = MockLLMProvider([
            {"content": "First response", "tool_calls": []},
            {"content": "Second response", "tool_calls": []},
        ])

        orchestrator = Orchestrator(
            llm=llm,
            memory=sqlite_provider,
            tool_executor=AsyncMock(return_value="ok"),
        )

        await orchestrator.process_message("First message")
        await orchestrator.process_message("Second message")

        # Check messages were saved
        context = await sqlite_provider.get_context()
        # Should have 4 messages: 2 user + 2 assistant
        assert len(context.messages) == 4

    @pytest.mark.asyncio
    async def test_session_buffer_provides_context(self, sqlite_provider):
        """Test that session buffer gives continuity within session."""
        llm = MockLLMProvider([
            {"content": "Response 1", "tool_calls": []},
            {"content": "Response 2", "tool_calls": []},
        ])

        orchestrator = Orchestrator(
            llm=llm,
            memory=sqlite_provider,
            tool_executor=AsyncMock(return_value="ok"),
        )

        await orchestrator.process_message("Message 1")
        await orchestrator.process_message("Message 2")

        # Second call should have first exchange in messages
        second_call_messages = llm.calls[1]["messages"]
        # Should include: context messages + session buffer (msg1 + resp1) + new msg2
        assert any("Message 1" in str(m) for m in second_call_messages)
        assert any("Response 1" in str(m) for m in second_call_messages)

    @pytest.mark.asyncio
    async def test_max_iterations_limit(self, sqlite_provider):
        """Test that tool loop respects max iterations."""
        # LLM always returns tool calls
        tool_call = MagicMock()
        tool_call.id = "tc_1"
        tool_call.name = "test_tool"
        tool_call.arguments = {}

        llm = MockLLMProvider([
            {"content": "", "tool_calls": [tool_call]},
            {"content": "", "tool_calls": [tool_call]},
            {"content": "", "tool_calls": [tool_call]},
            {"content": "", "tool_calls": [tool_call]},
            {"content": "", "tool_calls": [tool_call]},
        ])

        config = OrchestratorConfig(max_tool_iterations=3)
        orchestrator = Orchestrator(
            llm=llm,
            memory=sqlite_provider,
            tool_executor=AsyncMock(return_value="ok"),
            config=config,
        )

        result = await orchestrator.process_message("Test")

        # Should stop at 3 iterations
        assert result.total_iterations == 3
        assert llm.call_count == 3


class TestOrchestratorConfig:
    """Test OrchestratorConfig initialization."""

    def test_config_explicit_values(self):
        """Test that explicit values override defaults."""
        config = OrchestratorConfig(
            context_limit=10000,
            compact_threshold=0.50,
        )

        assert config.context_limit == 10000
        assert config.compact_threshold == 0.50

    def test_config_defaults(self):
        """Test default values."""
        config = OrchestratorConfig()

        # Just verify we get some reasonable defaults
        assert config.max_tool_iterations > 0
        assert config.max_tokens > 0
        assert config.context_limit > 0
        assert 0 < config.compact_threshold < 1
