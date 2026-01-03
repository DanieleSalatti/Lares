"""Tool Registry - manages tool schemas from MCP server.

Provides tool schemas to the Orchestrator, fetching from MCP as the source of truth.
Supports hot reload without restart.
"""

import asyncio
from typing import Any

import httpx
import structlog

log = structlog.get_logger()


class ToolRegistry:
    """Registry that fetches and caches tool schemas from MCP server."""

    def __init__(self, mcp_url: str = "http://localhost:8765"):
        self.mcp_url = mcp_url
        self._tools: list[dict[str, Any]] = []
        self._loaded = False

    async def load(self, retries: int = 5, delay: float = 2.0) -> None:
        """Load tool schemas from MCP server with retry logic.

        Args:
            retries: Number of retry attempts (default 5)
            delay: Seconds between retries (default 2.0)
        """
        for attempt in range(retries):
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    response = await client.get(f"{self.mcp_url}/tools")
                    response.raise_for_status()
                    data = response.json()
                    self._tools = data.get("tools", [])
                    self._loaded = True
                    log.info("tool_registry_loaded", tool_count=len(self._tools))
                    return
            except Exception as e:
                if attempt < retries - 1:
                    log.warning(
                        "tool_registry_load_retry",
                        attempt=attempt + 1,
                        max_retries=retries,
                        error=str(e),
                    )
                    await asyncio.sleep(delay)
                else:
                    log.error("tool_registry_load_failed", error=str(e))
                    if not self._loaded:
                        self._tools = []

    async def reload(self) -> int:
        """Reload tool schemas from MCP server.

        Returns:
            Number of tools loaded
        """
        await self.load(retries=1, delay=0)
        return len(self._tools)

    async def ensure_loaded(self) -> bool:
        """Ensure tools are loaded, retrying if needed.

        Call this before the first LLM call to handle race conditions
        where MCP server wasn't ready at startup.

        Returns:
            True if tools are available, False otherwise
        """
        if self._loaded and self._tools:
            return True
        await self.load()
        return bool(self._tools)

    def get_tools(self) -> list[dict[str, Any]]:
        """Get current tool schemas (Anthropic format).

        Returns:
            List of tool definitions with name, description, input_schema
        """
        return self._tools.copy()

    def get_tool(self, name: str) -> dict[str, Any] | None:
        """Get a specific tool by name.

        Args:
            name: Tool name to look up

        Returns:
            Tool definition or None if not found
        """
        for tool in self._tools:
            if tool.get("name") == name:
                return tool
        return None

    @property
    def tool_count(self) -> int:
        """Number of tools currently registered."""
        return len(self._tools)

    @property
    def tool_names(self) -> list[str]:
        """List of tool names."""
        return [t.get("name", "") for t in self._tools]
