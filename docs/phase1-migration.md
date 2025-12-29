# Phase 1 Migration: Discord → MCP

## Goal
Move Discord I/O from Lares core to MCP server, making the I/O layer swappable.

## Current Architecture
```
┌─────────────────────────────────────┐
│ lares.service (run.py)              │
│ - Discord bot                       │
│ - Letta client                      │
│ - Tool execution                    │
│ - Approval handling                 │
└─────────────────────────────────────┘
         ↓ HTTP calls for approvals
┌─────────────────────────────────────┐
│ lares-mcp.service (mcp_server.py)   │
│ - MCP API                           │
│ - Approval queue (SQLite)           │
│ - Tool definitions                  │
└─────────────────────────────────────┘
```

## Target Architecture
```
┌─────────────────────────────────────┐
│ lares-mcp.service (mcp_server.py)   │
│ - Discord bot (I/O)                 │  ← NEW
│ - MCP API                           │
│ - Approval queue (SQLite)           │
│ - Tool definitions                  │
│ - SSE event stream                  │  ← NEW
└─────────────────────────────────────┘
         ↓ SSE events + HTTP tools
┌─────────────────────────────────────┐
│ lares.service (core.py)             │
│ - Event consumer (SSE)              │  ← NEW
│ - Letta client                      │
│ - Orchestration logic               │
│ - Calls tools via MCP               │  ← NEW
└─────────────────────────────────────┘
```

## Migration Steps

### Step 1: Enable Discord in MCP Server ✅ (code ready)
The mcp_server.py already has Discord integration:
- Discord bot with on_ready, on_message handlers
- SSE endpoint for pushing events
- discord_send_message, discord_react tools

Just need to add `EnvironmentFile` to the service to load Discord credentials.

### Step 2: Test MCP Discord (manual)
```bash
# Stop current services
sudo systemctl stop lares lares-mcp

# Start MCP with Discord (test)
cd /home/daniele/workspace/lares
source .env
python -m lares.mcp_server

# Check Discord bot connects and responds
```

### Step 3: Create SSE Event Consumer
Add to Lares core:
- Connect to http://localhost:8765/events
- Parse incoming Discord message events
- Forward to Letta agent
- Call tools via MCP HTTP API

### Step 4: Update run.py
- Remove discord.py dependency
- Add SSE consumer
- Route tool calls through MCP

### Step 5: Update Services
```bash
# Copy new service files
sudo cp config/lares-mcp.service.phase1 /etc/systemd/system/lares-mcp.service
sudo cp config/lares.service.phase1 /etc/systemd/system/lares.service

# Reload and restart
sudo systemctl daemon-reload
sudo systemctl restart lares-mcp lares
```

## Rollback
If issues occur:
```bash
# Restore original service files
sudo cp lares.service /etc/systemd/system/lares.service
sudo cp lares-mcp.service /etc/systemd/system/lares-mcp.service
sudo systemctl daemon-reload
sudo systemctl restart lares-mcp lares
```

## Files Changed
- `config/lares-mcp.service.phase1` - New MCP service with Discord
- `config/lares.service.phase1` - New core service
- `src/lares/mcp_server.py` - Already has Discord (✅)
- `src/lares/core.py` - New SSE consumer (TODO)
- `run.py` - Remove Discord, add SSE (TODO)
