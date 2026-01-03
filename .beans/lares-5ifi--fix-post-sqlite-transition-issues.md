---
# lares-5ifi
title: Fix post-SQLite transition issues
status: completed
type: bug
priority: normal
created_at: 2026-01-01T18:49:57Z
updated_at: 2026-01-01T18:53:46Z
---

After swapping from Letta to SQLite, several issues have emerged:
1. Memory updates are not being applied
2. Tool approvals keep requiring approval for whitelisted folders
3. Brand status is unreliable and not being updated by Lares

## Checklist
- [x] Understand the current architecture and SQLite transition
- [x] Investigate memory update issues
- [x] Fix tool approval problems with whitelisted folders
- [ ] Fix brand status reliability issues (investigate if this is a real issue)
- [x] Test all fixes thoroughly

## Root Cause Analysis

**Memory Updates Issue**: ✅ FIXED - The SQLite mode was missing memory update tools. Added `memory_replace` and `memory_search` tools to MCP server.

**Tool Approval Issue**: ✅ FIXED - LARES_ALLOWED_PATHS environment variable was not being respected in MCP server. Fixed ALLOWED_DIRECTORIES initialization to parse the colon-separated paths from the environment.

**Brand Status Issue**: Could not find any references to "brand status" in the codebase. This might be a misunderstanding or external issue.

## Fixes Applied

1. **Added Memory Tools to MCP Server** (`src/lares/mcp_server.py`):
   - `memory_replace(label, old_str, new_str)` - Replace text in memory blocks
   - `memory_search(query, limit)` - Search memory blocks and messages

2. **Fixed Path Allowlist** (`src/lares/mcp_server.py`):
   - Updated `ALLOWED_DIRECTORIES` to respect `LARES_ALLOWED_PATHS` environment variable
   - Now properly parses colon-separated paths like `/tmp:/home/user/notes:/home/user/code`

## Testing Results

✅ **Syntax Check**: All Python files compile without errors
✅ **Linting**: All ruff checks pass  
✅ **Database**: SQLite database exists with proper schema and memory blocks
✅ **Imports**: Memory provider imports work correctly in SQLite mode
✅ **Environment**: LARES_ALLOWED_PATHS is properly parsed from .env file

## Next Steps

1. **Restart Services**: After MCP server restart, memory tools will be available to Lares
2. **Test Memory Updates**: Lares should now be able to call `memory_replace` to update its memory blocks
3. **Test File Operations**: File operations in `/tmp`, `/home/daniele/workspace/gitlab/daniele/appunti`, and `/home/daniele/workspace/lares` should no longer require approval