---
# lares-7ivd
title: Add num_ctx parameter to Ollama provider
status: completed
type: bug
priority: normal
created_at: 2026-01-06T04:37:32Z
updated_at: 2026-01-06T04:37:47Z
---

Ollama truncates to 4K despite model supporting 32K. Need to pass num_ctx in request options.