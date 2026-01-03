---
# lares-vdbo
title: Add perch time healthcheck message
status: completed
type: bug
priority: normal
created_at: 2026-01-01T23:05:20Z
updated_at: 2026-01-01T23:05:47Z
---

Perch time should always send a Discord message even when staying quiet, as a healthcheck so we know it didn't crash. Currently the LLM can complete perch_time_tick without calling any tools and no message is sent to Discord.