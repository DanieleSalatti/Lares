"""Tests for the Orchestrator."""


import pytest

from lares.orchestrator import Orchestrator, OrchestratorConfig
from lares.providers.llm import LLMProvider, LLMResponse, ToolCall
from lares.providers.memory import MemoryBlock, MemoryContext, MemoryProvider


class MockLLMProvider(LLMProvider):
    """Mock LLM provider for testing."""

    def __init__(self, responses: list[LLMResponse]):
        self.responses = responses
        self.call_count = 0

    async def initialize(self) -> None:
        pass

    async def shutdown(self) -> None:
        pass

    async def send(self, messages, system_prompt, tools=None, max_tokens=4096) -> LLMResponse:
        response = self.responses[min(self.call_count, len(self.responses) - 1)]
        self.call_count += 1
        return response


class MockMemoryProvider(MemoryProvider):
    """Mock memory provider for testing."""

    def __init__(self, context: MemoryContext | None = None):
        self._context = context or MemoryContext()
        self.messages_added = []

    async def initialize(self) -> None:
        pass

    async def shutdown(self) -> None:
        pass

    async def get_context(self) -> MemoryContext:
        return self._context

    async def add_message(self, role: str, content: str) -> None:
        self.messages_added.append({"role": role, "content": content})

    async def update_block(self, label: str, value: str) -> None:
        pass

    async def search(self, query: str, limit: int = 10) -> list:
        return []


class TestOrchestrator:
    """Tests for Orchestrator class."""

    @pytest.mark.asyncio
    async def test_simple_response_no_tools(self):
        """Orchestrator handles simple response without tool calls."""
        llm = MockLLMProvider([
            LLMResponse(content="Hello! How can I help?")
        ])
        memory = MockMemoryProvider()

        async def mock_tool_executor(name, args):
            return "tool result"

        orchestrator = Orchestrator(llm, memory, mock_tool_executor)
        result = await orchestrator.process_message("Hi there")

        assert result.response_text == "Hello! How can I help?"
        assert result.total_iterations == 1
        assert len(result.tool_calls_made) == 0

    @pytest.mark.asyncio
    async def test_single_tool_call(self):
        """Orchestrator handles a single tool call."""
        llm = MockLLMProvider([
            LLMResponse(
                content="Let me check that file.",
                tool_calls=[ToolCall(id="1", name="read_file", arguments={"path": "/test"})]
            ),
            LLMResponse(content="The file contains: test content")
        ])
        memory = MockMemoryProvider()

        async def mock_tool_executor(name, args):
            return "test content"

        orchestrator = Orchestrator(llm, memory, mock_tool_executor)
        result = await orchestrator.process_message("Read the file")

        assert result.response_text == "The file contains: test content"
        assert result.total_iterations == 2
        assert len(result.tool_calls_made) == 1
        assert result.tool_calls_made[0].name == "read_file"

    @pytest.mark.asyncio
    async def test_max_iterations_limit(self):
        """Orchestrator respects max iterations limit."""
        # LLM always returns tool calls
        llm = MockLLMProvider([
            LLMResponse(
                content="Calling tool...",
                tool_calls=[ToolCall(id="1", name="some_tool", arguments={})]
            )
        ] * 20)  # More than max
        memory = MockMemoryProvider()

        async def mock_tool_executor(name, args):
            return "result"

        config = OrchestratorConfig(max_tool_iterations=3)
        orchestrator = Orchestrator(llm, memory, mock_tool_executor, config)
        result = await orchestrator.process_message("Loop forever")

        assert result.total_iterations == 3
        assert len(result.tool_calls_made) == 3

    @pytest.mark.asyncio
    async def test_memory_context_used(self):
        """Orchestrator uses memory context for system prompt."""
        llm = MockLLMProvider([LLMResponse(content="Hi!")])
        memory = MockMemoryProvider(MemoryContext(
            base_instructions="You are Lares.",
            blocks=[MemoryBlock(label="persona", value="A helpful AI")]
        ))

        async def mock_tool_executor(name, args):
            return "result"

        orchestrator = Orchestrator(llm, memory, mock_tool_executor)
        await orchestrator.process_message("Hello")

        # LLM was called
        assert llm.call_count == 1

    @pytest.mark.asyncio
    async def test_messages_saved_to_memory(self):
        """Orchestrator saves conversation to memory."""
        llm = MockLLMProvider([LLMResponse(content="Response text")])
        memory = MockMemoryProvider()

        async def mock_tool_executor(name, args):
            return "result"

        orchestrator = Orchestrator(llm, memory, mock_tool_executor)
        await orchestrator.process_message("User input")

        assert len(memory.messages_added) == 2
        assert memory.messages_added[0] == {"role": "user", "content": "User input"}
        assert memory.messages_added[1] == {"role": "assistant", "content": "Response text"}


@pytest.mark.asyncio
async def test_orchestrator_session_buffer():
    """Test that orchestrator maintains session buffer for short-term memory."""
    llm = MockLLMProvider(responses=[
        LLMResponse(content="First response"),
        LLMResponse(content="Second response, remembering first"),
    ])
    memory = MockMemoryProvider()

    async def executor(name: str, args: dict) -> str:
        return "ok"

    orchestrator = Orchestrator(llm, memory, executor)

    # First message
    result1 = await orchestrator.process_message("Hello")
    assert result1.response_text == "First response"

    # Check session buffer has the exchange
    assert len(orchestrator._session_messages) == 2
    assert orchestrator._session_messages[0]["role"] == "user"
    assert orchestrator._session_messages[0]["content"] == "Hello"
    assert orchestrator._session_messages[1]["role"] == "assistant"
    assert orchestrator._session_messages[1]["content"] == "First response"

    # Second message
    result2 = await orchestrator.process_message("Remember me?")
    assert result2.response_text == "Second response, remembering first"

    # Session buffer should now have 4 messages
    assert len(orchestrator._session_messages) == 4

    # Clear session
    orchestrator.clear_session()
    assert len(orchestrator._session_messages) == 0


class TestBuildAssistantContent:
    """Tests for _build_assistant_content helper."""

    def test_with_response_text(self):
        """Response text is returned as-is."""
        from lares.orchestrator import Orchestrator, OrchestratorResult
        from lares.providers.llm import ToolCall

        # Create minimal orchestrator (won't actually use it)
        result = OrchestratorResult(response_text="Hello!")
        
        # Access the method via a mock
        content = Orchestrator._build_assistant_content(None, result)
        assert content == "Hello!"

    def test_with_tool_calls_only(self):
        """Tool-only responses get a summary."""
        from lares.orchestrator import Orchestrator, OrchestratorResult
        from lares.providers.llm import ToolCall

        result = OrchestratorResult(
            response_text="",
            tool_calls_made=[
                ToolCall(id="1", name="discord_send_message", arguments={}),
                ToolCall(id="2", name="memory_replace", arguments={}),
            ]
        )
        
        content = Orchestrator._build_assistant_content(None, result)
        assert "[Tool-only response:" in content
        assert "discord_send_message" in content
        assert "memory_replace" in content

    def test_empty_response(self):
        """Empty result returns empty string."""
        from lares.orchestrator import Orchestrator, OrchestratorResult

        result = OrchestratorResult()
        content = Orchestrator._build_assistant_content(None, result)
        assert content == ""
