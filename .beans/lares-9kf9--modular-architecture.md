---
# lares-9kf9
title: Modular Architecture
status: completed
type: milestone
created_at: 2025-12-27T20:49:23Z
updated_at: 2026-01-01T22:00:00Z
---

Decouple Lares into swappable modules: MCP for I/O, interfaces for Memory and LLM.

Goal: Be able to swap memory systems (Letta/Nocturne), LLMs (Claude/GPT/Local), and I/O channels (Discord/Telegram) independently.

## Phases (All Complete!)
1. ✅ Move Discord to MCP Server (lares-ya1u)
2. ✅ Extract LLM Interface (lares-4rma)
3. ✅ Extract Memory Interface (lares-su88)
4. ✅ Unify Approval System (lares-4kwh)

## Result
Lares is now modular:
- **I/O**: Discord runs in MCP server, Lares consumes events via SSE
- **LLM**: `LLMProvider` interface with `AnthropicLLMProvider` implementation
- **Memory**: `MemoryProvider` interface with `SqliteMemoryProvider` implementation
- **Approval**: Single approval flow through MCP server
- **Cleanup**: All Letta dependencies removed (lares-wmuf)