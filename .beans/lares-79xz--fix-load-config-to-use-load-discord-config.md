---
# lares-79xz
title: Fix load_config to use load_discord_config
status: completed
type: bug
priority: normal
created_at: 2026-01-05T18:11:38Z
updated_at: 2026-01-05T18:12:19Z
---

load_config() still requires Discord credentials and raises ValueError, but load_discord_config() handles them gracefully. Update load_config() to use load_discord_config() internally.