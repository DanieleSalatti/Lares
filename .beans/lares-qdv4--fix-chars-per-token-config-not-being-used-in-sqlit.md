---
# lares-qdv4
title: Fix CHARS_PER_TOKEN config not being used in sqlite.py
status: completed
type: bug
priority: normal
created_at: 2026-01-05T22:03:46Z
updated_at: 2026-01-05T22:05:04Z
---

sqlite.py has a hardcoded CHARS_PER_TOKEN=4 constant instead of using the value from MemoryConfig. Fix to use config.