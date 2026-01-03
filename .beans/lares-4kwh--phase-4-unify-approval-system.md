---
# lares-4kwh
title: 'Phase 4: Unify Approval System'
status: completed
type: epic
created_at: 2025-12-27T20:49:42Z
updated_at: 2026-01-01T22:00:00Z
parent: lares-9kf9
---

Consolidate all approvals through MCP queue.

## Checklist
- [x] Move all approval logic to MCP server
- [x] Remove Lares native approval flow
- [x] Ensure works across all I/O channels (Discord, future Telegram)

## Implementation
- `mcp_approval.py`: SQLite-backed `ApprovalQueue` with remembered patterns
- `mcp_server.py`: Approval endpoints (`/approvals/*`) and SSE notifications
- `main_mcp.py`: `ApprovalManager` polls MCP and posts approval requests to Discord
- Tools like `run_shell_command` and `post_to_bluesky` submit to approval queue
- Allowlist + remembered patterns for auto-approval
- Single approval flow: Tool → MCP Queue → Discord notification → User reaction → Execute

## Result
Single approval UX through MCP server. Works for any I/O channel that can consume SSE events.