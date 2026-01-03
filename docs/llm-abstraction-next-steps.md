# LLM Abstraction - Status

## Current State (2025-12-30)

### ✅ COMPLETED
- **Orchestrator** - Full LLM abstraction layer
- **SqliteMemoryProvider** - Letta-free memory storage
- **AnthropicLLMProvider** - Direct Claude API calls
- **AsyncToolExecutor** - MCP tool execution with approval workflow
- **Compaction service** - Context window management
- **Migration script** - `scripts/migrate_letta_to_sqlite.py`
- **Integration tests** - 173 tests passing
- **Configuration** - `MEMORY_PROVIDER=sqlite`, `USE_DIRECT_LLM=true`

### 🔄 READY TO ACTIVATE
To switch from Letta to SQLite/Direct LLM:

```bash
# Edit .env
USE_DIRECT_LLM=true

# Restart
sudo systemctl restart lares
```

To rollback:
```bash
USE_DIRECT_LLM=false
sudo systemctl restart lares
```

## Architecture

```
┌──────────────────────────────────────────────────────────┐
│                     Orchestrator                          │
│  (Process messages, manage tool loops, track iterations)  │
├──────────────────────────────────────────────────────────┤
│                                                          │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────┐  │
│  │ LLMProvider │  │MemoryProv. │  │  ToolExecutor   │  │
│  │ (Anthropic) │  │  (SQLite)  │  │ (MCP + Approval)│  │
│  └─────────────┘  └─────────────┘  └─────────────────┘  │
│                                                          │
└──────────────────────────────────────────────────────────┘
```

### Key Components

**Orchestrator** (`src/lares/orchestrator.py`)
- Main processing loop
- Handles tool call iterations
- Manages context building
- Tracks memory updates

**SqliteMemoryProvider** (`src/lares/providers/sqlite.py`)
- Messages table for conversation history
- Memory blocks for persistent state
- Summaries for compacted context

**Compaction** (`src/lares/compaction.py`)
- Summarizes old messages when context grows
- Configurable thresholds via env vars

## Configuration Options

```bash
# Memory provider
MEMORY_PROVIDER=sqlite           # or "letta"
SQLITE_DB_PATH=data/lares.db

# LLM mode
USE_DIRECT_LLM=true             # Use Orchestrator vs Letta's LLM

# Compaction
COMPACT_THRESHOLD=0.8           # Trigger at 80% context usage
COMPACT_TARGET=0.5              # Compact down to 50%

# LLM
ANTHROPIC_API_KEY=...
ANTHROPIC_MODEL=claude-sonnet-4-20250514
```

## Future Improvements

- [ ] Add OpenAI provider for model flexibility
- [ ] Semantic search via embeddings in SQLite
- [ ] Token counting for better context management
- [ ] Multi-session support
