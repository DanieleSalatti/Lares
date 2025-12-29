---
# lares-ya1u
title: 'Phase 1: Move Discord to MCP'
status: in-progress
type: epic
priority: normal
created_at: 2025-12-27T20:49:31Z
updated_at: 2025-12-27T22:57:00Z
parent: lares-9kf9
---

Move Discord client from Lares to MCP server, making I/O swappable.

## Checklist
- [x] Add Discord client to MCP server (lares-d370)
- [x] Create discord_send_message MCP tool
- [x] Create discord_react MCP tool
- [x] Add SSE endpoint for pushing incoming messages to Lares
- [ ] Update entry point to run both Discord + MCP
- [ ] Update Lares to receive messages via SSE instead of discord.py
- [ ] Remove Discord dependency from Lares core
- [ ] Test Telegram could be added same way

## Current Status
Most infrastructure ready! Just need to:
1. Enable the new entry point (runs Discord+MCP together)
2. Wire Lares to consume SSE events instead of direct discord.py

## Result
Discord becomes one of many possible I/O channels, all managed by MCP.
