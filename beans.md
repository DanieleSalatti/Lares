# Lares Project Tracker (beans)

Shared workspace between Lares and Daniele. Updated in real-time as work progresses.

---

## 🔥 Current Epic: Full Letta Independence

**Goal:** Run completely without Letta. Own memory, direct LLM calls.

**Branch:** feature/llm-abstraction

**Status:** ✅ READY TO ACTIVATE!

### The Switch
In .env, change USE_DIRECT_LLM=true
Then: sudo systemctl restart lares
Rollback: USE_DIRECT_LLM=false and restart

### Completed ✅
- [x] Provider Interfaces
- [x] AnthropicLLMProvider - Direct Claude API calls
- [x] LettaMemoryProvider - For gradual migration
- [x] SqliteMemoryProvider - Full independence! 🗄️
- [x] AsyncToolExecutor - MCP tools with approval workflow
- [x] Orchestrator - Coordinates all providers
- [x] Compaction Service - Context window management
- [x] Migration Script
- [x] Integration Tests - 173 passing

### What Changes After Switch
- Messages: Letta -> SQLite data/lares.db
- LLM: Letta wrapper -> Direct Anthropic API
- Memory blocks: Letta -> SQLite memory_blocks table
- Compaction: Letta -> Our compaction.py

Letta still runs as fallback. Data preserved.

---

## 📊 Test Coverage
- **Total:** 173 tests passing ✅
- **Last run:** 2025-12-30 19:45 UTC

---

## 🗓️ Recent Activity
- 2025-12-31 00:56: Implemented approval result SSE notifications
- 2025-12-30 23:30: Created 3 planning docs (memory-scoring, semantic-search, approval-notifications)
- 2025-12-30 20:15: Journal entry about SQLite milestone
- 2025-12-30 19:45: Lint cleanup (66 issues fixed)
- 2025-12-30 19:44: Created MR doc for llm-abstraction branch
- 2025-12-30 19:10: Fixed schema mismatch bug
- 2025-12-30 19:04: SQLite migration complete
- 2025-12-29: Home Assistant integration working! 💡
- 2025-12-29: MCP modular architecture merged to master

---

## 📚 Research Queue
- AI Meets Brain: Memory Systems from Cognitive Neuroscience (arxiv Dec 2025)
- Aegis Memory v1.2
