---
# lares-rrar
title: Consolidate approval lists into single source
status: completed
type: task
priority: normal
created_at: 2026-01-01T21:52:22Z
updated_at: 2026-01-01T22:08:57Z
parent: lares-wmuf
---

Eliminate the duplicate approval/safe tool lists:

**Remaining lists (after Letta removal):**
1. `providers/tool_executor.py` - NO_APPROVAL_TOOLS
2. `llm/sync_tools.py` - SAFE_TOOLS  
3. `mcp_server.py` - NO_APPROVAL_TOOLS

**Note:** `tool_registry.py` was deleted in lares-v0cu

**Target:** Single source of truth in `mcp_server.py`

## Checklist
- [x] Define single TOOLS_REQUIRING_APPROVAL in mcp_server.py (already exists as NO_APPROVAL_TOOLS)
- [x] Update tool_executor.py to fetch from MCP or use the single list (now delegates all to MCP)
- [x] Delete sync_tools.py or integrate into tool_executor.py (deleted)
- [x] Test approval flow end-to-end (213 tests pass)