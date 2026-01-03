---
# lares-3db2
title: Add NO_APPROVAL_TOOLS to MCP server
status: completed
type: bug
created_at: 2026-01-01T20:56:33Z
updated_at: 2026-01-01T20:56:33Z
---

Tools like memory_replace and memory_search were requiring approval even though they should not.

**Root cause:** The tool executor routes non-Discord tools to `/approvals` endpoint, which queues them for approval. Only shell commands had auto-approval logic.

**Fix:** Added NO_APPROVAL_TOOLS set in mcp_server.py that executes directly via `mcp.call_tool()` without queueing for approval.

Tools added to NO_APPROVAL_TOOLS:
- memory_replace
- memory_search  
- read_file
- list_directory
- read_rss_feed
- read_bluesky_user
- search_bluesky
- search_obsidian_notes
- read_obsidian_note

Also cleaned up sync_tools.py SAFE_TOOLS to only contain tools that can be executed locally (read_file, list_directory).

## Checklist
- [x] Add NO_APPROVAL_TOOLS set to mcp_server.py
- [x] Execute NO_APPROVAL_TOOLS directly via mcp.call_tool()
- [x] Clean up sync_tools.py SAFE_TOOLS
- [x] Tests pass