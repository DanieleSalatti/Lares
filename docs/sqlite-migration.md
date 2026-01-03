# SQLite Migration: Letta → Direct LLM Mode

## Overview
This migration switches Lares from using Letta as the LLM orchestrator to using direct Claude API calls with SQLite-backed memory. This provides:
- Independence from Letta server
- Full control over memory management
- Simpler architecture (no Docker dependency for Letta)
- Context compaction for long conversations

## Architecture Comparison

### Before (Letta Mode)
```
User → Discord → Lares → Letta → Claude API
                    ↓
               Letta's Memory (PostgreSQL)
```

### After (Direct LLM Mode)
```
User → Discord → Lares → Orchestrator → Claude API
                    ↓           ↓
               SQLite DB    MCP Server (tools)
```

## Pre-Migration Checklist

- [ ] Letta server is running (to export data)
- [ ] MCP server is running (`lares-mcp.service`)
- [ ] SQLite database directory exists (`data/`)
- [ ] `ANTHROPIC_API_KEY` in `.env`

## Migration Steps

### 1. Run the Migration Script
```bash
cd /home/daniele/workspace/lares

# Export memory blocks AND message history
MIGRATE_MESSAGES=true python scripts/migrate_letta_to_sqlite.py
```

This will:
- Connect to Letta and fetch all memory blocks
- Export message history (if MIGRATE_MESSAGES=true)
- Create `data/lares.db` with the exported data
- Show a summary of what was migrated

### 2. Verify the Export
```bash
# Check memory blocks
sqlite3 data/lares.db "SELECT label, LENGTH(content) as chars FROM memory_blocks"

# Check message count
sqlite3 data/lares.db "SELECT COUNT(*) FROM messages"

# Preview recent messages
sqlite3 data/lares.db "SELECT role, substr(content, 1, 50) FROM messages ORDER BY created_at DESC LIMIT 5"
```

### 3. Enable Direct LLM Mode
Edit `.env`:
```bash
USE_DIRECT_LLM=true
MEMORY_PROVIDER=sqlite  # optional, defaults to sqlite when USE_DIRECT_LLM=true
```

### 4. Restart Lares
```bash
sudo systemctl restart lares
```

### 5. Verify Operation
- Send a test message in Discord
- Check logs: `journalctl -u lares -f`
- Verify I respond and remember context

## Rollback

If issues occur, instant rollback:

```bash
# In .env, change:
USE_DIRECT_LLM=false

# Restart
sudo systemctl restart lares
```

Letta is still running and has all the original data. No data loss.

## Components

### Orchestrator (`orchestrator.py`)
Central coordinator that runs the tool loop:
- Calls Claude API directly
- Manages context window
- Executes tools (safe locally, others via MCP)

### SQLite Memory Provider (`providers/sqlite.py`)
Handles persistent storage:
- Memory blocks (persona, state, ideas, human)
- Message history with timestamps
- Summaries (for compaction)

### Tool Registry (`providers/tool_registry.py`)
Fetches tool schemas from MCP server at startup

### Tool Executor (`providers/tool_executor.py`)
Executes tools:
- Safe tools (discord_react, memory_replace, etc.) run locally
- Unsafe tools queue to MCP's `/approvals` endpoint

### Compaction Service (`compaction.py`)
Manages context window:
- Summarizes old messages when context gets full
- Preserves important information while reducing tokens

## Configuration

| Env Variable | Default | Description |
|--------------|---------|-------------|
| `USE_DIRECT_LLM` | `false` | Enable direct LLM mode |
| `MEMORY_PROVIDER` | `sqlite` | Memory backend |
| `SQLITE_DB_PATH` | `data/lares.db` | Database location |
| `CONTEXT_LIMIT` | `50000` | Max context tokens |
| `COMPACT_THRESHOLD` | `0.70` | Trigger compaction at 70% |
| `ANTHROPIC_MODEL` | `claude-sonnet-4-20250514` | Model to use |

## Troubleshooting

### "No tools available"
- Check MCP server is running: `systemctl status lares-mcp`
- Check MCP_URL in config matches server

### "Tool requires approval" but nothing in Discord
- Check ApprovalManager is polling: look for `approval_poll` in logs
- Check MCP `/approvals/pending` endpoint

### Memory not persisting
- Check SQLite file exists and is writable
- Check logs for SQLite errors

### Context too large
- Compaction should trigger automatically
- Can manually reduce by summarizing old messages
