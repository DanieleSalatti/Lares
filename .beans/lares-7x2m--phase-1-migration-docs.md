---
# lares-7x2m
title: Phase 1 migration documentation
status: done
type: task
priority: normal
created_at: 2025-12-27T23:05:00Z
updated_at: 2025-12-27T23:05:00Z
parent: lares-ya1u
---

Created migration plan and service file drafts for Phase 1.

## Deliverables
- [x] config/lares-mcp.service.phase1 - MCP with Discord enabled
- [x] config/lares.service.phase1 - Core service depending on MCP  
- [x] docs/phase1-migration.md - Step-by-step migration guide

## Key Finding
MCP server's Discord code is already complete!
Just need `EnvironmentFile=/path/to/.env` in the service to enable it.
