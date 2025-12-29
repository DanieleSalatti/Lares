---
# lares-d370
title: Add Discord client to MCP server
status: in-progress
type: task
priority: high
created_at: 2025-12-27T20:51:31Z
updated_at: 2025-12-27T22:57:00Z
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
- [ ] Update entry point to run Discord + MCP together
- [ ] Test end-to-end

## Blocker
Entry point change ready but needs testing. Changes how system starts up.
Code is in mcp_server.py but entry point still runs MCP solo.

## Notes
See docs/phase1-discord-mcp-design.md for full design.
