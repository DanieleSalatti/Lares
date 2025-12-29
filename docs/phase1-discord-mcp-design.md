# Phase 1: Move Discord to MCP - Design Document

## Current Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  Lares (discord_bot.py)                                     │
│  ├── Discord client (discord.py library)                    │
│  │   ├── on_message → sends to Letta                        │
│  │   ├── on_reaction_add → approval handling                │
│  │   └── send/react → direct Discord API calls              │
│  ├── Letta client (memory + LLM)                            │
│  ├── Tool executor (approval flow)                          │
│  ├── Perch time scheduler                                   │
│  └── MCP bridge (polls approvals from MCP server)           │
└─────────────────────────────────────────────────────────────┘
                            │
                            │ HTTP (tool calls)
                            ▼
┌─────────────────────────────────────────────────────────────┐
│  MCP Server (mcp_server.py)                                 │
│  ├── Tools: shell, files, RSS, BlueSky, Obsidian            │
│  └── Approval queue (SQLite)                                │
└─────────────────────────────────────────────────────────────┘
```

**Problems:**
- Discord is embedded in Lares - adding Telegram means duplicating logic
- Two approval flows (Lares native + MCP queue)
- Can't run Lares without Discord

## Target Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  MCP Server (all I/O)                                       │
│  ├── Discord client                                         │
│  │   ├── on_message → push to SSE /events endpoint          │
│  │   └── approval reactions → update approval queue         │
│  ├── Tools:                                                 │
│  │   ├── discord_send_message(channel_id?, content)         │
│  │   ├── discord_react(message_id, emoji)                   │
│  │   ├── shell, files, RSS, BlueSky, Obsidian...            │
│  └── Approval queue (SQLite + Discord reactions)            │
└──────────────────────────┬──────────────────────────────────┘
                           │ SSE (events)
                           ▼
┌─────────────────────────────────────────────────────────────┐
│  Lares Core (brain)                                         │
│  ├── SSE listener (receives messages from MCP)              │
│  ├── Letta client (memory + LLM)                            │
│  ├── Tool execution loop (calls MCP tools)                  │
│  └── Perch time scheduler                                   │
└─────────────────────────────────────────────────────────────┘
```

## Implementation Steps

### Step 1: Add Discord to MCP Server

Add Discord client to `mcp_server.py`:

```python
import discord
from discord.ext import commands

# Discord bot setup
discord_intents = discord.Intents.default()
discord_intents.message_content = True
discord_intents.reactions = True
discord_bot = commands.Bot(command_prefix="!", intents=discord_intents)

# Store for sending messages
_discord_channel: discord.TextChannel | None = None

@discord_bot.event
async def on_ready():
    global _discord_channel
    channel_id = int(os.getenv("DISCORD_CHANNEL_ID"))
    _discord_channel = discord_bot.get_channel(channel_id)
    log.info("discord_connected", channel=_discord_channel.name)
```

### Step 2: Add Discord Tools to MCP

```python
@mcp.tool()
async def discord_send_message(content: str, reply_to: str | None = None) -> str:
    """Send a message to the Discord channel."""
    if not _discord_channel:
        return "Error: Discord not connected"
    
    if reply_to:
        msg = await _discord_channel.fetch_message(int(reply_to))
        await msg.reply(content)
    else:
        await _discord_channel.send(content)
    
    return "Message sent"

@mcp.tool()
async def discord_react(message_id: str, emoji: str) -> str:
    """React to a Discord message with an emoji."""
    if not _discord_channel:
        return "Error: Discord not connected"
    
    msg = await _discord_channel.fetch_message(int(message_id))
    await msg.add_reaction(emoji)
    return f"Reacted with {emoji}"
```

### Step 3: Add SSE Events Endpoint

```python
from starlette.responses import StreamingResponse
import asyncio
import json

# Event queue for SSE clients
event_queues: list[asyncio.Queue] = []

async def event_generator(queue: asyncio.Queue):
    """Generate SSE events from queue."""
    try:
        while True:
            event = await queue.get()
            yield f"data: {json.dumps(event)}\n\n"
    except asyncio.CancelledError:
        pass

@mcp.custom_route("/events", methods=["GET"])
async def events_endpoint(request: Request):
    """SSE endpoint for Lares to receive events."""
    queue = asyncio.Queue()
    event_queues.append(queue)
    
    async def cleanup():
        event_queues.remove(queue)
    
    return StreamingResponse(
        event_generator(queue),
        media_type="text/event-stream",
        background=cleanup
    )

async def push_event(event_type: str, data: dict):
    """Push event to all connected SSE clients."""
    event = {"type": event_type, **data}
    for queue in event_queues:
        await queue.put(event)
```

### Step 4: Push Discord Events to SSE

```python
@discord_bot.event
async def on_message(message):
    # Ignore own messages
    if message.author == discord_bot.user:
        return
    
    # Only messages in target channel
    if message.channel.id != _discord_channel.id:
        return
    
    # Push to SSE
    await push_event("discord_message", {
        "message_id": str(message.id),
        "author": message.author.name,
        "author_id": str(message.author.id),
        "content": message.content,
        "timestamp": message.created_at.isoformat(),
    })

@discord_bot.event
async def on_reaction_add(reaction, user):
    # Ignore own reactions
    if user == discord_bot.user:
        return
    
    # Check if this is an approval reaction
    # ... handle approval queue updates ...
    
    # Push to SSE
    await push_event("discord_reaction", {
        "message_id": str(reaction.message.id),
        "user": user.name,
        "emoji": str(reaction.emoji),
    })
```

### Step 5: Update Lares Core

Replace Discord listener with SSE listener:

```python
import aiohttp

class LaresCore:
    def __init__(self, config, letta_client, agent_id):
        self.config = config
        self.letta_client = letta_client
        self.agent_id = agent_id
        self.mcp_url = config.mcp_url  # e.g., "http://localhost:8765"
    
    async def run(self):
        """Main run loop - listen to SSE events."""
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{self.mcp_url}/events") as response:
                async for line in response.content:
                    if line.startswith(b"data: "):
                        event = json.loads(line[6:])
                        await self.handle_event(event)
    
    async def handle_event(self, event):
        """Handle incoming event from MCP."""
        if event["type"] == "discord_message":
            await self.handle_message(event)
        elif event["type"] == "perch_tick":
            await self.handle_perch_time()
    
    async def handle_message(self, event):
        """Process a message through LLM."""
        # Build context, call Letta, execute tools...
        pass
```

### Step 6: Move Perch Time to MCP

Perch time can be a scheduled event in MCP that pushes to SSE:

```python
from apscheduler.schedulers.asyncio import AsyncIOScheduler

scheduler = AsyncIOScheduler()

@scheduler.scheduled_job("interval", minutes=30)
async def perch_tick():
    """Push perch time event to Lares."""
    await push_event("perch_tick", {
        "timestamp": datetime.utcnow().isoformat(),
    })
```

## Testing Plan

1. Start MCP server with Discord enabled
2. Start Lares Core (no Discord dependency)
3. Send message in Discord
4. Verify: MCP receives → pushes SSE → Lares handles → calls MCP tools → Discord response

## Migration Notes

- Can run both old and new in parallel during transition
- Environment variable to toggle: `LARES_USE_MCP_DISCORD=true`
- Fallback to embedded Discord if MCP unavailable
