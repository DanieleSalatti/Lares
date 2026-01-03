---
# lares-rj44
title: Swappable LLM Providers
status: completed
type: feature
priority: normal
created_at: 2026-01-02T20:36:23Z
updated_at: 2026-01-02T20:41:32Z
---

Enable switching between LLM providers (Anthropic, OpenAI, Ollama) via environment variables.

## Checklist
- [x] Create LLM provider factory (src/lares/providers/llm_factory.py)
- [x] Update orchestrator_factory.py to use factory
- [x] Create OpenAI provider (src/lares/providers/openai.py)
- [x] Create Ollama provider (src/lares/providers/ollama.py)
- [x] Test with each provider (Anthropic tested end-to-end; OpenAI/Ollama tested via import)

## Env vars
- LLM_PROVIDER: anthropic|openai|ollama
- ANTHROPIC_API_KEY, ANTHROPIC_MODEL
- OPENAI_API_KEY, OPENAI_MODEL  
- OLLAMA_BASE_URL, OLLAMA_MODEL