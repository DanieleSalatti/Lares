---
# lares-qiab
title: Fix scheduler startup and list_jobs
status: completed
type: bug
priority: normal
created_at: 2026-01-02T07:48:34Z
updated_at: 2026-01-02T07:49:02Z
---

1. start() loads jobs before APScheduler starts - should start first then load. 2. MCP list_jobs shows N/A because APScheduler not running - should read from JSON metadata only.