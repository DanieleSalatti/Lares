"""Orchestrator - the central coordinator for Lares.

The Orchestrator owns the tool loop and coordinates:
- LLM Provider (Claude, GPT, etc.)
- Memory Provider (Letta, SQLite, etc.)
- Tool Provider (MCP server via ToolRegistry)
- Compaction (memory maintenance)
"""

import os
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import structlog

from .compaction import CompactionService
from .providers.llm import LLMProvider, ToolCall
from .providers.memory import MemoryContext, MemoryProvider
from .providers.sqlite import SqliteMemoryProvider

if TYPE_CHECKING:
    from .providers.tool_registry import ToolRegistry

log = structlog.get_logger()


@dataclass
class OrchestratorConfig:
    """Configuration for the Orchestrator."""
    max_tool_iterations: int = 10
    max_tokens: int = 4096
    # Context limit from env var, default 50k
    context_limit: int = int(os.getenv("CONTEXT_LIMIT", "50000"))
    # Compact threshold from env var, default 70%
    compact_threshold: float = float(os.getenv("COMPACT_THRESHOLD", "0.70"))


@dataclass
class OrchestratorResult:
    """Result from processing a message."""
    response_text: str = ""
    tool_calls_made: list[ToolCall] = field(default_factory=list)
    total_iterations: int = 0
    tokens_used: int = 0
    compaction_performed: bool = False


# Type for async tool executor
ToolExecutor = Callable[[str, dict[str, Any]], Awaitable[str]]


class Orchestrator:
    """Central coordinator that runs the tool loop.

    Coordinates between LLM, Memory, and Tool providers.

    Maintains a session buffer of recent messages to provide short-term
    memory within a session, even if the memory provider doesn't persist
    assistant messages immediately.
    """

    def __init__(
        self,
        llm: LLMProvider,
        memory: MemoryProvider,
        tool_executor: ToolExecutor,
        config: OrchestratorConfig | None = None,
        tool_registry: "ToolRegistry | None" = None,
    ):
        self.llm = llm
        self.memory = memory
        self.tool_executor = tool_executor
        self.config = config or OrchestratorConfig()
        self.tool_registry = tool_registry
        # Session buffer for short-term memory
        self._session_messages: list[dict[str, Any]] = []
        # Compaction service (only for SQLite provider)
        self._compaction: CompactionService | None = None
        if isinstance(memory, SqliteMemoryProvider):
            self._compaction = CompactionService(
                memory=memory,
                llm=llm,
                context_limit=self.config.context_limit,
                compact_threshold=self.config.compact_threshold,
            )
            log.info(
                "compaction_enabled",
                context_limit=self.config.context_limit,
                compact_threshold=self.config.compact_threshold,
            )

    async def process_message(self, user_message: str) -> OrchestratorResult:
        """Process a user message through the full tool loop.

        1. Check context size, compact if needed
        2. Get context from memory
        3. Build prompt and call LLM
        4. If tool calls: execute and loop
        5. Return final response
        """
        result = OrchestratorResult()

        # Pre-check: ensure we have headroom for this request
        if self._compaction:
            if await self._compaction.needs_compaction():
                log.info("compaction_triggered", reason="pre_request_check")
                await self._compaction.compact()
                result.compaction_performed = True

        # Get context from memory provider
        context = await self.memory.get_context()
        log.debug("got_memory_context", tokens=context.total_tokens)

        # Build messages list: context messages + session buffer + new message
        messages = context.messages.copy()
        messages.extend(self._session_messages)
        messages.append({"role": "user", "content": user_message})

        # Build system prompt from memory blocks
        system_prompt = self._build_system_prompt(context)

        # Get tools from registry (preferred) or context (fallback)
        tools = await self._get_tools(context)

        # Tool loop
        iteration = 0
        while iteration < self.config.max_tool_iterations:
            iteration += 1
            result.total_iterations = iteration

            log.debug("llm_iteration", iteration=iteration)

            # Call LLM
            response = await self.llm.send(
                messages=messages,
                system_prompt=system_prompt,
                tools=tools if tools else None,
                max_tokens=self.config.max_tokens,
            )

            # Track usage
            if response.usage:
                result.tokens_used += response.usage.get("total_tokens", 0)

            # If no tool calls, we're done
            if not response.has_tool_calls:
                result.response_text = response.content
                break

            # Execute tool calls
            tool_results = await self._execute_tools(response.tool_calls)
            result.tool_calls_made.extend(response.tool_calls)

            # Add assistant message with tool calls
            messages.append({
                "role": "assistant",
                "content": response.content,
                "tool_calls": [
                    {"id": tc.id, "name": tc.name, "arguments": tc.arguments}
                    for tc in response.tool_calls
                ]
            })

            # Add tool results
            for tc, tr in zip(response.tool_calls, tool_results):
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": tr,
                })

        # Build assistant content (includes tool activity if no text response)
        assistant_content = self._build_assistant_content(result)

        # Add to session buffer for short-term memory
        self._session_messages.append({"role": "user", "content": user_message})
        if assistant_content:
            self._session_messages.append({"role": "assistant", "content": assistant_content})

        # Save to memory provider (for long-term persistence)
        await self.memory.add_message("user", user_message)
        if assistant_content:
            await self.memory.add_message("assistant", assistant_content)

        log.debug("session_buffer_size", messages=len(self._session_messages))
        return result

    def _build_assistant_content(self, result: OrchestratorResult) -> str:
        """Build assistant message content including tool activity.

        If there's response text, use it. If there were tool calls but no text,
        create a summary of tool activity so the context isn't lost.
        """
        if result.response_text:
            return result.response_text
        elif result.tool_calls_made:
            # No text response but tools were used - summarize the activity
            tool_names = [tc.name for tc in result.tool_calls_made]
            return f"[Tool-only response: {', '.join(tool_names)}]"
        else:
            return ""

    async def _get_tools(self, context: MemoryContext) -> list[dict[str, Any]]:
        """Get tools from registry or context.

        Prefers tool_registry if available, falls back to context.tools.
        Will retry loading if registry has no tools (handles startup race).
        """
        if self.tool_registry:
            tools = self.tool_registry.get_tools()
            if tools:
                log.debug("using_registry_tools", count=len(tools))
                return tools
            await self.tool_registry.ensure_loaded()
            tools = self.tool_registry.get_tools()
            if tools:
                log.info("tools_loaded_on_retry", count=len(tools))
                return tools

        if context.tools:
            log.debug("using_context_tools", count=len(context.tools))
            return context.tools

        log.warning("no_tools_available")
        return []

    async def _execute_tools(self, tool_calls: list[ToolCall]) -> list[str]:
        """Execute a list of tool calls and return results."""
        results = []
        for tc in tool_calls:
            log.info("executing_tool", tool=tc.name)
            try:
                result = await self.tool_executor(tc.name, tc.arguments)
                results.append(result)
            except Exception as e:
                log.error("tool_execution_error", tool=tc.name, error=str(e))
                results.append(f"Error executing {tc.name}: {e}")
        return results

    def _build_system_prompt(self, context: MemoryContext) -> str:
        """Build system prompt from memory context."""
        parts = []

        if context.base_instructions:
            parts.append(context.base_instructions)

        if context.blocks:
            parts.append("\n<memory_blocks>")
            for block in context.blocks:
                parts.append(f"\n<{block.label}>")
                if block.description:
                    parts.append(f"<description>{block.description}</description>")
                parts.append(f"<value>{block.value}</value>")
                parts.append(f"</{block.label}>")
            parts.append("\n</memory_blocks>")

        return "\n".join(parts)

    def clear_session(self) -> None:
        """Clear the session buffer.

        Useful after a restart or when starting a new conversation context.
        """
        self._session_messages.clear()
        log.info("session_buffer_cleared")
