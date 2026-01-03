# Merge Request: LLM Abstraction & SQLite Memory

## Summary
Complete independence from Letta's LLM - use Claude directly with our own SQLite-based memory system.

## Key Changes

### New Providers
- **SqliteMemoryProvider** - Full memory system without Letta
  - Messages, memory blocks, summaries tables
  - Session-based conversation history
  - Compatible schema with existing provider interface

- **AnthropicLLMProvider** - Direct Claude API calls
  - No Letta wrapper, just Claude
  - Supports tool calling, streaming (future)

### Orchestrator Enhancements
- **Session buffer** - Short-term memory for current conversation
- **Compaction service** - Summarizes old messages when context grows
- **Configurable thresholds** - `COMPACT_THRESHOLD`, `COMPACT_TARGET`
- **Approval result notifications** - SSE events for approve/deny outcomes

### Migration Support
- **Migration script** (`scripts/migrate_letta_to_sqlite.py`)
  - Exports memory blocks from Letta
  - Imports into SQLite with provider-compatible schema
  - Safe: doesn't modify Letta, just copies

### Configuration
```bash
# To activate (in .env):
USE_DIRECT_LLM=true
LARES_DB_PATH=data/lares.db

# To rollback:
USE_DIRECT_LLM=false
```

## Test Coverage
- **178 tests** (up from 103 at branch start)
- New test files:
  - `test_sqlite_provider.py` (9 tests)
  - `test_orchestrator_integration.py` (7 tests)
  - `test_compaction.py` (enhanced)
  - `test_approval_results.py` (7 tests)

## Code Quality
- **Lint-clean**: All ruff checks pass
- **49 commits** on feature branch
- Refactored for line length compliance
- Helper functions extracted for clarity

## Commits Highlights
- Orchestrator and provider interfaces
- LettaMemoryProvider (for gradual migration)
- AnthropicLLMProvider (direct Claude)
- AsyncToolExecutor
- SQLite schema and provider
- Compaction service
- Migration script
- Integration tests
- Approval result notifications (SSE)
- Code quality fixes

## Risk Mitigation
- **Instant rollback**: Change one env var and restart
- **Letta preserved**: Still running, data intact
- **Dual path**: Code supports both Letta and SQLite paths
- **Tested**: 178 tests including integration tests
- **Lint-clean**: No code quality regressions

## What's Next (after merge & activation)
1. Monitor for stability
2. Add semantic search (embeddings in SQLite)
3. Add OpenAI provider for model flexibility
4. Implement memory scoring (access tracking, decay)
5. Potentially remove Letta entirely once stable
