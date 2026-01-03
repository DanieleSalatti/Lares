---
# lares-kn12
title: Fix startup race condition between lares and lares-mcp
status: completed
type: bug
created_at: 2026-01-01T22:55:35Z
updated_at: 2026-01-01T23:00:00Z
---

Tools fail to load at startup because MCP server isn't ready yet. Added retry logic to handle the race condition.

## Problem
- Lares starts and tries to load tools from MCP at http://localhost:8765/tools
- MCP server isn't ready yet (race condition)
- tool_registry_load_failed error, tools_loaded=0
- Lares continues but with no tools available

## Solution
Added retry logic at two levels:

1. **ToolRegistry.load()** - Now retries 5 times with 2-second delays when MCP server isn't ready
2. **ToolRegistry.ensure_loaded()** - New method to check/retry before first LLM call
3. **Orchestrator._get_tools()** - Now async, calls ensure_loaded() if no tools available

## Files Changed
- src/lares/providers/tool_registry.py - Added retry logic and ensure_loaded method
- src/lares/orchestrator.py - Made _get_tools async with fallback retry

## Testing
- All 202 tests pass
- ruff and mypy pass

## Checklist
- [x] Add retry logic to tool registry loading
- [x] Ensure tools are available before first LLM call
- [ ] Test with systemd restart