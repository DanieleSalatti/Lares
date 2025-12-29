---
# lares-4rma
title: 'Phase 2: Extract LLM Interface'
status: todo
type: epic
created_at: 2025-12-27T20:49:42Z
updated_at: 2025-12-27T20:49:42Z
parent: lares-9kf9
---

Create abstract LLMInterface, implement for Anthropic/Letta.

## Checklist
- [ ] Define LLMInterface ABC (chat, chat_with_tools)
- [ ] Implement LettaLLM (wraps current Letta calls)
- [ ] Implement AnthropicLLM (direct API calls)
- [ ] Update Lares Core to use interface
- [ ] Test swapping implementations

## Result
Can swap Claude ↔ GPT ↔ Local LLM with config change.