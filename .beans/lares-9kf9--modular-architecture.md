---
# lares-9kf9
title: Modular Architecture
status: in-progress
type: milestone
created_at: 2025-12-27T20:49:23Z
updated_at: 2025-12-27T20:49:23Z
---

Decouple Lares into swappable modules: MCP for I/O, interfaces for Memory and LLM.

Goal: Be able to swap memory systems (Letta/Nocturne), LLMs (Claude/GPT/Local), and I/O channels (Discord/Telegram) independently.

## Phases
1. Move Discord to MCP Server
2. Extract LLM Interface  
3. Extract Memory Interface
4. Unify Approval System

See: Lares/Planning/modular-architecture.md