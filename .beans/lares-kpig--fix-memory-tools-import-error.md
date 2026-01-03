---
# lares-kpig
title: Fix memory tools import error
status: completed
type: bug
priority: normal
created_at: 2026-01-01T23:12:14Z
updated_at: 2026-01-01T23:15:59Z
---

Memory tools (memory_replace, memory_update) in mcp_server.py are trying to import create_memory_provider from orchestrator_factory, but that function doesn't exist. Need to either add the function or update the memory tools to use a different approach.