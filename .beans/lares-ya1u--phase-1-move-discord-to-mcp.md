---
# lares-ya1u
title: 'Phase 1: Move Discord to MCP'
status: completed
type: epic
priority: normal
created_at: 2025-12-27T20:49:31Z
updated_at: 2026-01-01T22:00:00Z
parent: lares-9kf9
---

Move Discord client from Lares to MCP server, making I/O swappable.

## Checklist
- [x] Add Discord client to MCP server (lares-d370)
- [x] Create discord_send_message MCP tool
- [x] Create discord_react MCP tool
- [x] Add SSE endpoint for pushing incoming messages to Lares
- [x] Update entry point to run both Discord + MCP
- [x] Update Lares to receive messages via SSE instead of discord.py
- [x] Remove Discord dependency from Lares core
- [ ] Test Telegram could be added same way (future work, not blocking)

## Implementation
- `mcp_server.py`: Discord bot + MCP server in single process via `run_with_discord()`
- `main_mcp.py`: Lares core that consumes SSE events from MCP
- `sse_consumer.py`: SSEConsumer + DiscordClient classes for event handling
- Service files: `lares-mcp.service` runs MCP+Discord, `lares.service` runs core

## Result
Discord is now an I/O channel managed by MCP. Telegram support is architecturally possible.
