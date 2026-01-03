---
# lares-4rma
title: 'Phase 2: Extract LLM Interface'
status: completed
type: epic
created_at: 2025-12-27T20:49:42Z
updated_at: 2026-01-01T22:00:00Z
parent: lares-9kf9
---

Create abstract LLMInterface, implement for Anthropic.

## Checklist
- [x] Define LLMInterface ABC (chat, chat_with_tools)
- [x] Implement AnthropicLLM (direct API calls)
- [x] Update Lares Core to use interface
- [x] Test swapping implementations (tests pass)

## Implementation
- `providers/llm.py`: `LLMProvider` ABC with `send()`, `LLMResponse`, `ToolCall` dataclasses
- `providers/anthropic.py`: `AnthropicLLMProvider` implementation
- `orchestrator.py`: Uses `LLMProvider` interface (line 18, 64-65)
- `orchestrator_factory.py`: Creates `AnthropicLLMProvider` (line 61)
- Tests: `test_llm_provider.py` (7 tests, all pass)

## Note
LettaLLM not implemented - Letta was removed as a backend. Additional providers (OpenAI, local) can be added by implementing `LLMProvider`.

## Result
Can swap Claude ↔ GPT ↔ Local LLM by implementing `LLMProvider` interface.