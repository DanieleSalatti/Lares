<p align="center">
  <img src="docs/logo.png" alt="Lares logo" width="250">
</p>

# Lares

A stateful AI agent with persistent memory - your household guardian.

Inspired by [Strix](https://timkellogg.me/blog/2025/12/15/strix), Lares is an ambient AI assistant that maintains memory across conversations, learns about you over time, and can act proactively.

## Features

- **Persistent Memory**: Uses [Letta](https://letta.com) for long-term memory that survives restarts
- **Discord Interface**: Chat with Lares through Discord
- **Memory Blocks**: Organized memory for identity, human preferences, state, and ideas
- **Autonomous Operation**: "Perch time" ticks every hour for self-reflection and proactive actions
- **Scheduled Tasks**: Set reminders and recurring jobs with flexible scheduling
- **Self-Management**: Can restart itself for updates and maintenance
- **Tool System**: File operations, shell commands, RSS feeds, BlueSky integration, and more
- **Extensible**: Designed for adding new interfaces (Telegram, web) and capabilities

## Quick Start

### Prerequisites

- Python 3.11+
- A [Letta Cloud](https://app.letta.com) account (or self-hosted Letta)
- A Discord bot token

### Installation

```bash
# Clone the repository
git clone https://git.v37.io/daniele/lares.git
cd lares

# Create virtual environment
python -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -e ".[dev]"

# (Optional) Enable self-restart capability
# This allows Lares to restart itself for updates and maintenance
sudo bash scripts/setup-sudoers.sh
```

### Configuration

```bash
# Copy example config
cp .env.example .env

# Edit .env with your credentials:
# - LETTA_API_KEY: From app.letta.com (or use LETTA_BASE_URL for self-hosted)
# - DISCORD_BOT_TOKEN: From Discord Developer Portal
# - DISCORD_CHANNEL_ID: The channel where Lares will listen
# - ANTHROPIC_API_KEY: For the LLM (required for self-hosted Letta)

# Optional integrations:
# - BLUESKY_HANDLE: Your BlueSky handle (e.g., user.bsky.social)
# - BLUESKY_APP_PASSWORD: App password from BlueSky settings
# - OBSIDIAN_VAULT_PATH: Path to your Obsidian vault folder
# - LARES_MAX_TOOL_ITERATIONS: Max tool iterations per message (default: 10)
```

### Running

#### Development Mode

For testing and development:

```bash
# Activate virtual environment
source .venv/bin/activate

# Run Lares directly
python run.py
# or if installed: lares
```

On first run, Lares will create a new agent and print an `LARES_AGENT_ID` - add this to your `.env` to persist the agent across restarts.

#### Production Mode (systemd)

For production deployment with auto-start on boot:

```bash
# Copy the service file
sudo cp lares.service /etc/systemd/system/

# Edit the service file to match your setup
sudo systemctl edit lares.service
# Update User, WorkingDirectory, and paths as needed

# Enable and start the service
sudo systemctl enable lares.service
sudo systemctl start lares.service

# View logs
journalctl -u lares.service -f

# Common management commands:
sudo systemctl status lares.service  # Check status
sudo systemctl restart lares.service # Restart Lares
sudo systemctl stop lares.service    # Stop Lares
journalctl -u lares.service -n 50    # View last 50 log lines
```

The systemd service:
- Automatically starts Letta Docker container before Lares
- Restarts on failure
- Runs with proper virtual environment
- Logs to systemd journal
- Persists across reboots when enabled

## Self-Hosting Letta

You can run Letta locally with Docker:

```bash
docker run \
  -v ~/.letta/.persist/pgdata:/var/lib/postgresql/data \
  -p 8283:8283 \
  -e ANTHROPIC_API_KEY="your_key" \
  letta/letta:latest
```

Then set in your `.env`:
```
LETTA_BASE_URL=http://localhost:8283
```

## Approval Workflows

Lares implements two types of approval workflows for sensitive operations:

### Command Approval (Synchronous)
When Lares tries to run a shell command not in the allowlist:
1. Sends approval request to Discord with ✅/❌ reactions
2. **Waits up to 5 minutes** for your response
3. If approved: adds command to allowlist and executes
4. If denied or timeout: returns error to Lares

### BlueSky Post Approval (Asynchronous)
When Lares wants to post to BlueSky:
1. Sends approval request to Discord with post preview
2. **Returns immediately** - Lares continues other work
3. You can approve/deny anytime (even hours later)
4. When approved: post is sent to BlueSky
5. When denied: post is discarded

This async pattern prevents Lares from being blocked while waiting for approval.

## Self-Restart Capability

Lares can restart itself when needed (e.g., after updates, configuration changes, or for maintenance). This requires passwordless sudo access for the restart command.

### Setup

Run the setup script during installation (requires sudo):

```bash
sudo bash scripts/setup-sudoers.sh
```

This configures passwordless sudo for **only** the specific command:
```bash
systemctl restart lares.service
```

### Security Note

The sudoers configuration is minimal and scoped:
- Only allows restarting the `lares.service` systemd unit
- No other sudo commands are affected
- Standard Linux pattern for service self-management

### Usage

Once configured, Lares can restart itself by calling the `restart_lares()` tool:

```python
# Lares can decide when to restart, such as:
# - After git pull to apply updates
# - When .env configuration changes
# - For periodic maintenance during perch time
# - Recovery from suspected issues
```

## Development

```bash
# Run tests
pytest

# Run linter
ruff check src/

# Run type checker
mypy src/
```

## Architecture

```
src/lares/
├── config.py          # Configuration management
├── memory.py          # Letta integration and memory blocks
├── discord_bot.py     # Discord interface and perch time
├── scheduler.py       # Job scheduling with APScheduler
├── tool_registry.py   # Tool execution and approval workflow
├── response_parser.py # Discord response parsing (reactions, messages)
├── time_utils.py      # Time context and timezone handling
├── bluesky_reader.py  # BlueSky API client
├── rss_reader.py      # RSS/Atom feed parser
├── obsidian.py        # Obsidian vault integration (optional)
├── tools/             # Tool implementations
│   ├── filesystem.py      # read_file, write_file
│   ├── shell.py           # run_command
│   ├── discord.py         # send_message, react
│   ├── scheduler.py       # schedule_job, remove_job, list_jobs
│   ├── rss.py             # read_rss_feed
│   ├── bluesky.py         # read_bluesky_user, search_bluesky, post_to_bluesky
│   ├── system_management.py  # restart_lares
│   └── tool_creation.py   # create_tool (dynamic tool creation)
└── main.py            # Entry point
```

### Memory Blocks

Lares uses four memory blocks:

| Block | Purpose |
|-------|---------|
| `persona` | Lares's identity and personality |
| `human` | Information about you |
| `state` | Current working memory and tasks |
| `ideas` | Feature ideas and future plans |

### Available Tools

Lares has access to 14 registered tools, plus optional Obsidian integration:

#### Core Tools (14)

| Tool | Description |
|------|-------------|
| `run_command` | Execute shell commands with approval workflow (working_dir optional) |
| `read_file` | Read files from the filesystem |
| `write_file` | Create or modify files |
| `schedule_job` | Schedule reminders and recurring tasks (supports cron, intervals, datetime) |
| `remove_job` | Remove scheduled jobs |
| `list_jobs` | List all scheduled jobs |
| `read_rss_feed` | Read RSS/Atom feeds |
| `read_bluesky_user` | Read posts from a BlueSky user |
| `search_bluesky` | Search BlueSky posts |
| `post_to_bluesky` | Post to BlueSky (async approval workflow) |
| `discord_send_message` | Send messages to Discord (reply mode optional) |
| `discord_react` | React to messages with emoji |
| `restart_lares` | Restart the Lares service |
| `create_tool` | Create new tools from Python code |

#### Obsidian Integration (6, optional)

When `OBSIDIAN_VAULT_PATH` is configured, these additional tools become available:

| Tool | Description |
|------|-------------|
| `read_note` | Read a note from Obsidian vault |
| `write_note` | Create or modify notes in vault |
| `append_to_note` | Append content to existing notes |
| `search_notes` | Search vault for text content |
| `list_notes` | List notes in directory |
| `add_journal_entry` | Add timestamped journal entries |

## Roadmap

Future enhancements under consideration:

- Multi-modal awareness (images, voice)
- Local-first operation for privacy
- Multiple LLM backend support
- Telegram and web interfaces
- Richer memory with semantic search
- Plugin system for extensibility
- Proactive context gathering

## License

**PolyForm Noncommercial License 1.0.0**

This software is licensed under the PolyForm Noncommercial License 1.0.0, a modern license designed specifically for noncommercial open source.

### What this means:
- ✅ **Free for personal use** - Individuals can use, modify, and share for hobby/personal projects
- ✅ **Free for education** - Students, teachers, and educational institutions
- ✅ **Free for nonprofits** - Charities and registered nonprofit organizations
- ✅ **Free for research** - Public research organizations and experiments
- ✅ **Free for government** - Government institutions and public services
- ❌ **NOT free for commercial use** - No commercial or for-profit use
- ❌ **NOT free for companies** - Corporations cannot use, even internally
- ❌ **NOT free as a service** - Cannot host or offer as SaaS

### Why this license?
Lares is a labor of love meant to empower individuals, not enrich corporations. The PolyForm Noncommercial license provides crystal-clear terms that prevent any commercial exploitation while keeping the software freely available for personal, educational, and charitable use.

See [LICENSE](LICENSE) for full terms.
