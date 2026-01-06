---
# lares-fds2
title: Fix missing complete() method in LLM providers
status: completed
type: bug
priority: normal
created_at: 2026-01-06T04:32:19Z
updated_at: 2026-01-06T04:32:39Z
---

Compaction code calls llm.complete() but LLMProvider only has send(). Need to add complete() method to base class and implement in Ollama/Anthropic providers.