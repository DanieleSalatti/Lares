---
# lares-d370
title: Add Discord client to MCP server
status: completed
type: task
priority: high
created_at: 2025-12-27T20:51:31Z
updated_at: 2026-01-01T22:00:00Z
parent: lares-ya1u
---

Add discord.py client to mcp_server.py

## Checklist
- [x] Add discord imports and setup
- [x] Initialize bot with proper intents
- [x] Add SSE event queue for real-time events
- [x] Add /events SSE endpoint
- [x] Add discord_send_message tool
- [x] Add discord_react tool
- [x] Update entry point to run Discord + MCP together
- [x] Test end-to-end

## Implementation
- `mcp_server.py` has `run_with_discord()` entry point (line 1109)
- Service files in `services/` use `python -m lares.mcp_server` and `python -m lares.main_mcp`
- `main_mcp.py` consumes SSE events and processes through Orchestrator

## Notes
See docs/phase1-discord-mcp-design.md for full design.
