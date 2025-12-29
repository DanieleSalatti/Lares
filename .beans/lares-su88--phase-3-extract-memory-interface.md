---
# lares-su88
title: 'Phase 3: Extract Memory Interface'
status: todo
type: epic
created_at: 2025-12-27T20:49:42Z
updated_at: 2025-12-27T20:49:42Z
parent: lares-9kf9
---

Create abstract MemoryInterface, implement for Letta.

## Checklist
- [ ] Define MemoryInterface ABC (read_block, write_block, search, etc.)
- [ ] Implement LettaMemory (wraps current Letta memory)
- [ ] Update Lares Core to use interface
- [ ] Research Nocturne/MemMachine implementations

## Result
Can swap Letta ↔ Nocturne ↔ MemMachine with config change.