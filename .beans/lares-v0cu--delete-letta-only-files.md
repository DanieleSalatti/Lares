---
# lares-v0cu
title: Delete Letta-only files
status: completed
type: task
priority: normal
created_at: 2026-01-01T21:52:20Z
updated_at: 2026-01-01T22:03:03Z
parent: lares-wmuf
---

Delete files that are entirely Letta-specific:

- `providers/letta.py` - LettaMemoryProvider
- `tool_registry.py` - Letta ToolExecutor, TOOL_SOURCES, register_tools_with_letta (NOT providers/tool_registry.py)
- `llm/handler.py` - DirectLLMHandler (uses Letta for context)
- `llm/memory_bridge.py` - Letta memory bridge
- `llm/tool_bridge.py` - Sync ToolBridge (legacy)
- `memory.py` - Letta-specific memory functions

## Checklist
- [x] Delete providers/letta.py
- [x] Delete tool_registry.py
- [x] Delete llm/handler.py
- [x] Delete llm/memory_bridge.py
- [x] Delete llm/tool_bridge.py
- [x] Delete memory.py
- [x] Run tests to find broken imports
- [x] Fix broken imports

## Also completed
- Deleted Letta-specific tests (test_memory_compaction.py, test_context_update.py, test_context_analysis.py, test_orphan_filtering.py)
- Updated test_providers.py, test_llm_provider.py, test_main_mcp.py, test_config.py to remove Letta references
- Updated providers/__init__.py to remove LettaMemoryProvider
- Updated llm/__init__.py to remove memory_bridge imports