---
# lares-cm6s
title: Fix post-SQLite transition issues
status: completed
type: bug
priority: normal
created_at: 2026-01-01T20:13:18Z
updated_at: 2026-01-01T20:14:53Z
---

Three issues found after SQLite migration:

1. **Lares not responding to Discord messages** - Service is crashing on startup due to missing `handle_scheduled_job` method in LaresCore (main_mcp.py:562)
2. **Memory updates possibly broken** - Need to verify memory_replace tool and block updates work correctly 
3. **Context not fully available during perch ticks** - Need to verify context building includes all memory blocks

Root cause of #1: The `handle_scheduled_job` method exists at line 472-479 but is incorrectly placed INSIDE the `perch_time_tick` method due to indentation error.

## Checklist
- [x] Fix indentation of handle_scheduled_job method (move outside perch_time_tick)
- [x] Verify memory_replace tool works correctly (checked code + DB has blocks)
- [x] Verify perch time gets full context from memory provider (checked _build_system_prompt)
- [x] Test the fixes work (252 tests pass, ruff passes)