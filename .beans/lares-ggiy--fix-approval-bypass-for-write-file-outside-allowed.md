---
# lares-ggiy
title: Fix approval bypass for write_file outside allowed paths
status: completed
type: bug
priority: normal
created_at: 2026-01-02T02:50:34Z
updated_at: 2026-01-02T02:50:59Z
---

When approving write_file for paths outside allowed directories, the approval succeeds but execution still fails because mcp.call_tool re-runs the path check. Need internal _execute_write_file function similar to _execute_shell_command.