---
# lares-8pm2
title: SSE event consumer module
status: done
type: task
priority: normal
created_at: 2025-12-27T23:15:00Z
updated_at: 2025-12-27T23:16:00Z
parent: lares-ya1u
---

Created src/lares/sse_consumer.py for consuming Discord events from MCP.

## Features
- [x] SSEConsumer class with async event loop
- [x] DiscordMessageEvent and DiscordReactionEvent dataclasses
- [x] Handler registration (on_message, on_reaction)
- [x] Auto-reconnect on connection loss
- [x] Lint-clean code

## Next Steps
- Integrate with run.py or new core.py entry point
- Wire up handlers to forward messages to Letta
