---
# lares-zt7p
title: Refactor mcp_server.py to use config.py
status: completed
type: task
priority: normal
created_at: 2026-01-05T18:01:52Z
updated_at: 2026-01-05T18:03:10Z
---

Extend config.py to include all env vars that mcp_server.py needs, then refactor mcp_server.py to use the config instead of direct os.getenv calls. Keep graceful Discord disabling behavior.