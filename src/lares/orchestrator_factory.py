"""Factory for creating Orchestrator with configured providers."""

import os

import structlog

from lares.config import load_memory_config
from lares.orchestrator import Orchestrator, OrchestratorConfig
from lares.providers.llm_factory import create_llm_provider
from lares.providers.sqlite import SqliteMemoryProvider
from lares.providers.tool_executor import AsyncToolExecutor
from lares.providers.tool_registry import ToolRegistry

log = structlog.get_logger()


def _load_base_instructions() -> str:
    """Load base instructions from file or return default."""
    instructions_path = os.getenv("BASE_INSTRUCTIONS_PATH", "prompts/base_instructions.md")
    if os.path.exists(instructions_path):
        with open(instructions_path) as f:
            return f.read()

    return """You are Lares, a helpful AI assistant with persistent memory.
You can use tools to help accomplish tasks. Be thoughtful and proactive."""


async def create_memory_provider(
    memory_provider_type: str = "sqlite",
    sqlite_path: str | None = None,
) -> SqliteMemoryProvider:
    """Create a memory provider instance.

    Args:
        memory_provider_type: Type of memory provider (only 'sqlite' supported)
        sqlite_path: Path to SQLite database

    Returns:
        Initialized memory provider
    """
    if memory_provider_type != "sqlite":
        raise ValueError(f"Unsupported memory provider: {memory_provider_type}")

    path = sqlite_path or os.getenv("SQLITE_DB_PATH") or "data/lares.db"
    instructions = _load_base_instructions()
    memory = SqliteMemoryProvider(db_path=path, base_instructions=instructions)
    await memory.initialize()
    return memory


async def create_tool_registry(mcp_url: str) -> ToolRegistry:
    """Create and load a ToolRegistry from MCP server.

    Args:
        mcp_url: URL of the MCP server

    Returns:
        Initialized ToolRegistry with tools loaded
    """
    registry = ToolRegistry(mcp_url)
    await registry.load()
    log.info("tool_registry_created", mcp_url=mcp_url, tool_count=registry.tool_count)
    return registry


async def create_orchestrator(
    discord=None,
    mcp_url: str | None = None,
    model: str | None = None,
) -> Orchestrator:
    """Create and initialize an Orchestrator with providers.

    Args:
        discord: Discord client for sending messages/reactions
        mcp_url: MCP server URL for approval-required tools
        model: LLM model to use (defaults to claude-opus-4-5)

    Returns:
        Initialized Orchestrator ready for use
    """
    memory_config = load_memory_config()

    llm = create_llm_provider(model=model)
    await llm.initialize()
    llm_model = llm.model

    path = memory_config.sqlite_path or os.getenv("SQLITE_DB_PATH", "data/lares.db")
    instructions = _load_base_instructions()
    memory = SqliteMemoryProvider(db_path=path, base_instructions=instructions)
    await memory.initialize()
    log.info("memory_provider_created", type="sqlite", path=path)

    tool_executor = AsyncToolExecutor(discord=discord, mcp_url=mcp_url)

    tool_registry = None
    if mcp_url:
        tool_registry = await create_tool_registry(mcp_url)

    config = OrchestratorConfig(
        max_tool_iterations=int(os.getenv("LARES_MAX_TOOL_ITERATIONS", "10")),
        context_limit=memory_config.context_limit,
        compact_threshold=memory_config.compact_threshold,
    )

    orchestrator = Orchestrator(
        llm, memory, tool_executor.execute, config, tool_registry=tool_registry
    )

    orchestrator._tool_executor_instance = tool_executor

    log.info(
        "orchestrator_created",
        model=llm_model,
        memory_provider="sqlite",
        context_limit=memory_config.context_limit,
        compact_threshold=memory_config.compact_threshold,
        tools_loaded=tool_registry.tool_count if tool_registry else 0,
    )

    return orchestrator
