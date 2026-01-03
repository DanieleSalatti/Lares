---
# lares-dmml
title: "Fix approval \U0001F513 reaction and path boundary bug"
status: completed
type: bug
created_at: 2026-01-01T20:27:07Z
updated_at: 2026-01-01T20:27:07Z
---

Two additional fixes:

1. **Approval 🔓 reaction inconsistency** - Message text showed '🔓 Approve & Remember' for all tools, but the reaction was only added for shell commands. Fixed by:
   - Making footer conditional on tool type
   - Adding error logging for failed reactions

2. **Path boundary bug in sync_tools.py** - The `is_path_allowed` function used `startswith` without ensuring directory boundary, allowing /tmpfoo to match /tmp. Fixed by checking `startswith(allowed_real + os.sep)`.

## Checklist
- [x] Fix message footer to only show 🔓 option for shell commands  
- [x] Add logging for reaction failures
- [x] Fix sync_tools.py path boundary bug
- [x] Tests pass