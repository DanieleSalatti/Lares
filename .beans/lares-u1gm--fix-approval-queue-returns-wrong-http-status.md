---
# lares-u1gm
title: Fix approval queue returns wrong HTTP status
status: completed
type: bug
priority: normal
created_at: 2026-01-02T01:33:34Z
updated_at: 2026-01-02T01:34:02Z
---

When a tool needs approval, MCP returns HTTP 200 with {id, status: pending}, but tool_executor expects HTTP 202 for pending. This causes the tool to return 'OK' instead of 'Queued for approval', making Lares think the tool succeeded when it's actually pending.