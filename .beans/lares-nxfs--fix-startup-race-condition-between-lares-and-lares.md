---
# lares-nxfs
title: Fix startup race condition between lares and lares-mcp services
status: completed
type: bug
priority: normal
created_at: 2026-01-01T22:47:29Z
updated_at: 2026-01-01T22:48:02Z
---

The lares service crashes on startup because it tries to connect to MCP before the server is ready. Need to add connection retry logic to DiscordClient methods.