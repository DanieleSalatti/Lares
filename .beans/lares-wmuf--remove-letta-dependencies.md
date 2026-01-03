---
# lares-wmuf
title: Remove Letta Dependencies
status: completed
type: epic
created_at: 2026-01-01T21:52:01Z
updated_at: 2026-01-01T22:10:00Z
parent: lares-9kf9
---

Remove all Letta-specific code from Lares now that we're using SQLite memory provider.

**Context:** Letta was the original memory backend but we've migrated to SQLite. The Letta code paths are now dead code that adds confusion and maintenance burden.

## Checklist
- [x] Delete Letta provider and related files (no `memory.py` exists)
- [x] Clean up imports and references
- [x] Consolidate duplicate approval lists (commit 185ef0c)
- [x] Simplify tool execution flow
- [x] Remove `letta-client` from pyproject.toml dependencies
- [x] Delete `monitoring_patch.py` (dead code referencing non-existent `lares.memory`)

## Result
All Letta dependencies removed. 202 tests pass.