---
# lares-ob7w
title: Clean up mixed Letta/non-Letta files
status: completed
type: task
priority: normal
created_at: 2026-01-01T21:52:20Z
updated_at: 2026-01-01T22:03:18Z
parent: lares-wmuf
---

Remove Letta references from files that have both Letta and non-Letta code:

- `main_mcp.py` - Remove Letta imports and async wrappers (lines 17-57)
- `orchestrator_factory.py` - Remove LettaMemoryProvider import and creation (lines 10, 46-52)
- `config.py` - Remove Letta config options

## Checklist
- [x] Clean main_mcp.py
- [x] Clean orchestrator_factory.py  
- [x] Clean config.py
- [x] Run tests

## Summary
- Rewrote main_mcp.py to use Orchestrator exclusively (removed Letta fallback code paths)
- Simplified orchestrator_factory.py to only create SQLite memory provider
- Removed LettaConfig from config.py, simplified Config dataclass
- Removed deprecated `use_direct_llm` flag (now always direct)
- All 220 tests pass