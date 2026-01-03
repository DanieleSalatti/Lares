---
# lares-b4b6
title: Audit and refactor tool execution architecture
status: completed
type: task
priority: normal
created_at: 2026-01-01T21:47:13Z
updated_at: 2026-01-01T21:52:37Z
parent: lares-wmuf
---

Review the tool execution flow holistically to eliminate duplicate approval lists and legacy Letta code paths.

**Context:** Moving away from Letta. Currently have duplicate NO_APPROVAL_TOOLS in mcp_server.py and tool_executor.py which is bad architecture.

## Checklist
- [x] Map current tool execution flow
- [x] Identify all approval/safe tool lists
- [x] Identify Letta-specific code that can be removed
- [x] Propose consolidated architecture
- [x] Implement refactoring (split into sub-tasks under lares-wmuf epic)

## Analysis

### Current Tool Execution Flow (Messy)

```
User Message
    ↓
main_mcp.py (LaresMCPCore)
    ↓
orchestrator.py (Orchestrator)
    ↓
providers/tool_executor.py (AsyncToolExecutor)
    ├── Discord tools → direct Discord API
    ├── is_safe_tool() → sync_tools.py (local execution)
    ├── NO_APPROVAL_TOOLS → mcp_server.py /approvals (auto-approve)
    └── Other tools → mcp_server.py /approvals (queue for approval)
                          ↓
                    mcp_server.py checks NO_APPROVAL_TOOLS again!
                          ↓
                    Either auto-approve or queue
```

### Duplicate Approval/Safe Tool Lists (5 total!)

| File | List | Tools |
|------|------|-------|
| `providers/tool_executor.py:11` | `NO_APPROVAL_TOOLS` | memory_replace, memory_search, read_file, list_directory |
| `llm/sync_tools.py:16` | `SAFE_TOOLS` | read_file, list_directory |
| `mcp_server.py:256` | `NO_APPROVAL_TOOLS` | memory_replace, memory_search, read_file, list_directory |
| `tool_registry.py:772` | `tools_not_requiring_approval` | 15 tools (Letta-specific) |
| `mcp_server.py` | Shell allowlist | Separate mechanism for shell commands |

### Letta-Specific Code to Remove

1. **`providers/letta.py`** - Entire file (LettaMemoryProvider)
2. **`tool_registry.py`** - Entire file is Letta-specific (ToolExecutor class, TOOL_SOURCES, register_tools_with_letta)
3. **`llm/handler.py`** - DirectLLMHandler calls Letta for context
4. **`llm/memory_bridge.py`** - Letta memory bridge  
5. **`llm/tool_bridge.py`** - Sync ToolBridge (legacy)
6. **`memory.py`** - Letta-specific memory functions
7. **`main_mcp.py:17-57`** - Letta imports and async wrappers
8. **`orchestrator_factory.py:10,46-52`** - Letta provider creation
9. **`config.py`** - Letta config options

### Files with Mixed Letta/Non-Letta Code

- `main_mcp.py` - Has Letta imports but mostly orchestrator-based
- `orchestrator_factory.py` - Creates both Letta and SQLite providers

### Proposed Clean Architecture

```
User Message
    ↓
main_mcp.py (LaresMCPCore) 
    ↓
orchestrator.py (Orchestrator)
    ↓
providers/tool_executor.py (AsyncToolExecutor) - SINGLE SOURCE OF TRUTH
    ├── Discord tools → direct via DiscordActions protocol
    ├── Local tools (read_file, list_directory) → execute locally
    └── MCP tools → mcp_server.py /tools/execute (new endpoint)
                         ↓
                   Tool definitions in mcp_server.py
                   Single approval list: TOOLS_REQUIRING_APPROVAL
```

**Key Changes:**
1. Remove Letta provider entirely (use SQLite only)
2. Single `TOOLS_REQUIRING_APPROVAL` set in `mcp_server.py`
3. `tool_executor.py` becomes thin router to MCP
4. Delete `tool_registry.py` (use `providers/tool_registry.py` only)
5. New MCP endpoint `/tools/execute` that handles all tool execution
6. Remove all sync tool implementations (let MCP handle everything)