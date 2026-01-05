# Restart Awareness Feature

## Files Created
- `src/lares/restart_tracker.py` - Already written ✅

## Changes Needed in main_mcp.py

### 1. Add import at top:
```python
from lares.restart_tracker import record_startup, get_restart_context
```

### 2. In run() function, after config loading, add:
```python
    # Record startup and get restart context
    startup_info = record_startup(reason="normal")
    restart_context = get_restart_context(startup_info)
    if restart_context:
        log.info("restart_detected", context=restart_context)
```

### 3. Pass restart_context to LaresCore:
```python
    core = LaresCore(config, discord, mcp_url, orchestrator, restart_context=restart_context)
```

### 4. Update LaresCore.__init__:
```python
    def __init__(
        self,
        config,
        discord: DiscordClient,
        mcp_url: str,
        orchestrator,
        restart_context: str | None = None,
    ):
        ...
        self._restart_context = restart_context
        self._restart_context_sent = False
```

### 5. Inject restart context into first message, in handle_message():
After formatting the message, before processing:
```python
        # Inject restart context if this is first message after restart
        if self._restart_context and not self._restart_context_sent:
            formatted = f"{self._restart_context}\n\n{formatted}"
            self._restart_context_sent = True
```

### 6. Also inject into first perch tick:
In perch_time_tick(), modify perch_prompt:
```python
        # Inject restart context if this is first tick after restart  
        if self._restart_context and not self._restart_context_sent:
            perch_prompt = f"{self._restart_context}\n\n{perch_prompt}"
            self._restart_context_sent = True
```

## Startup message change
Change:
```python
await discord.send_message("🏛️ Lares online (MCP mode)")
```
To:
```python
startup_msg = "🏛️ Lares online (MCP mode)"
if restart_context:
    startup_msg += " [restarted]"
await discord.send_message(startup_msg)
```

## Usage
When Lares starts after a restart, the first message/perch tick will include:
```
[RESTART NOTICE] You were restarted. Previous session started 5 minutes ago (reason: normal). Some context from before the restart may be lost - check your diary/state if needed.
```
