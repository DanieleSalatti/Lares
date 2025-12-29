# Merge Request: Modular Architecture (Phase 1 Foundation)

## Summary
This branch lays the groundwork for the modular architecture redesign, with a focus on moving Discord I/O to the MCP server.

## Changes

### New Features
- **Approve & Remember (🔓)** - Shell commands can now be approved AND have their patterns saved for future auto-approval
  - Stored in SQLite, persists across restarts
  - Patterns: curl, python3, sed, cd, uname remembered

- **SSE Event Consumer** (`src/lares/sse_consumer.py`) - New module for receiving Discord events from MCP server
  - Async event loop with auto-reconnect
  - Type-safe event dataclasses
  - Handler registration pattern

- **Discord in MCP Server** - MCP server now has Discord client ready to enable
  - SSE endpoint at `/events` for pushing Discord events
  - `discord_send_message` and `discord_react` tools
  - Just needs `EnvironmentFile` in systemd to activate

### Documentation
- `docs/phase1-migration.md` - Step-by-step migration guide
- `config/lares-mcp.service.phase1` - Draft MCP service with Discord
- `config/lares.service.phase1` - Draft core service depending on MCP

### Bug Fixes
- Show 🔓 option for both `run_command` and `run_shell_command` (tool name mismatch)
- Test isolation for remembered commands
- MCP health check endpoint

## Test Coverage
- **70 tests** (up from ~35 before this branch)
- New test files:
  - `tests/test_sse_consumer.py` (11 tests)
  - `tests/test_mcp_approval.py` (expanded)

## What's NOT in this MR
- Actual activation of Discord in MCP server (requires service restart)
- Modification of run.py to consume SSE events (that's the next step)

## Next Steps (after merge)
1. Update systemd services to enable Discord in MCP
2. Modify run.py to use SSE consumer instead of direct Discord
3. Test end-to-end with new architecture
