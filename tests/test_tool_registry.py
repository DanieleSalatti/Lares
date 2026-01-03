"""Tests for ToolRegistry."""

import pytest

from lares.providers.tool_registry import ToolRegistry


class TestToolRegistry:
    """Tests for ToolRegistry class."""

    def test_init(self):
        """Test registry initialization."""
        registry = ToolRegistry("http://localhost:8765")
        assert registry.mcp_url == "http://localhost:8765"
        assert registry._tools == []
        assert registry._loaded is False

    def test_get_tools_returns_copy(self):
        """Test that get_tools returns a copy."""
        registry = ToolRegistry("http://localhost:8765")
        registry._tools = [{"name": "test", "description": "test", "input_schema": {}}]
        
        tools = registry.get_tools()
        tools.append({"name": "new"})
        
        # Original should be unchanged
        assert len(registry._tools) == 1

    def test_get_tool_found(self):
        """Test get_tool returns tool when found."""
        registry = ToolRegistry("http://localhost:8765")
        registry._tools = [
            {"name": "tool1", "description": "first", "input_schema": {}},
            {"name": "tool2", "description": "second", "input_schema": {}},
        ]
        
        tool = registry.get_tool("tool2")
        assert tool is not None
        assert tool["description"] == "second"

    def test_get_tool_not_found(self):
        """Test get_tool returns None when not found."""
        registry = ToolRegistry("http://localhost:8765")
        registry._tools = [{"name": "tool1", "description": "first", "input_schema": {}}]
        
        tool = registry.get_tool("nonexistent")
        assert tool is None

    def test_tool_names(self):
        """Test tool_names property."""
        registry = ToolRegistry("http://localhost:8765")
        registry._tools = [
            {"name": "alpha", "description": "a", "input_schema": {}},
            {"name": "beta", "description": "b", "input_schema": {}},
        ]
        
        names = registry.tool_names
        assert names == ["alpha", "beta"]

    def test_tool_count(self):
        """Test tool_count property."""
        registry = ToolRegistry("http://localhost:8765")
        assert registry.tool_count == 0
        
        registry._tools = [{"name": "a"}, {"name": "b"}, {"name": "c"}]
        assert registry.tool_count == 3

    @pytest.mark.asyncio
    async def test_load_failure_preserves_existing(self):
        """Test that load failure preserves existing tools."""
        registry = ToolRegistry("http://invalid-url:9999")
        registry._tools = [{"name": "existing", "description": "test", "input_schema": {}}]
        registry._loaded = True
        
        # This should fail but preserve existing tools
        await registry.load()
        
        # Should still have the existing tool
        assert len(registry._tools) == 1
        assert registry._tools[0]["name"] == "existing"

    @pytest.mark.asyncio
    async def test_load_empty_on_initial_failure(self):
        """Test that initial load failure results in empty tools."""
        registry = ToolRegistry("http://invalid-url:9999")
        
        await registry.load()
        
        # Should have empty tools
        assert registry._tools == []
        assert registry._loaded is False
