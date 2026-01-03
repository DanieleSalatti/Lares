---
# lares-impg
title: Fix memory tools requiring approval
status: completed
type: bug
priority: normal
created_at: 2026-01-01T21:38:20Z
updated_at: 2026-01-01T21:39:00Z
---

Memory tools (memory_replace, memory_search) are showing approval prompts in Discord even though they should auto-approve.

**Root cause:** AsyncToolExecutor in tool_executor.py checks is_safe_tool() from sync_tools.py, which only includes read_file and list_directory. Memory tools fall through to _queue_for_approval().

The mcp_server.py has NO_APPROVAL_TOOLS but that only applies when requests go directly to /approvals endpoint - not when AsyncToolExecutor calls it.

**Fix:** Add NO_APPROVAL_TOOLS to tool_executor.py that routes directly through MCP (not approval queue).