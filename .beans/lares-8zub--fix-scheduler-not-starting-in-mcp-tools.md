---
# lares-8zub
title: Fix scheduler not starting in MCP tools
status: completed
type: bug
priority: normal
created_at: 2026-01-02T07:26:07Z
updated_at: 2026-01-02T07:30:54Z
---

Two schedulers running in separate processes. MCP tools should proxy to main_mcp via HTTP endpoints instead of running their own scheduler.