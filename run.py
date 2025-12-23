#!/usr/bin/env python3
"""Simple runner script for Lares."""

import sys

sys.path.insert(0, 'src')

import asyncio

from lares.config import load_config
from lares.discord_bot import create_bot
from lares.logging_config import get_logger, setup_logging
from lares.memory import create_letta_client, get_or_create_agent
from lares.tool_registry import register_tools_with_letta


async def run() -> None:
    """Async main function."""
    print("Starting Lares...", flush=True)

    config = load_config()
    print(f"Config loaded. Agent: {config.agent_id}", flush=True)

    # Initialize logging system
    setup_logging(config)
    log = get_logger("main")
    log.info("lares_starting", version="0.1.0", config_loaded=True)

    client = create_letta_client(config)
    log.info("letta_client_ready")
    print("Letta client ready", flush=True)

    # Get or create agent (also updates model if changed)
    agent_id = await get_or_create_agent(client, config)
    log.info("agent_ready", agent_id=agent_id)
    print(f"Agent ready: {agent_id}", flush=True)

    # Register tools with Letta
    registered_tools = register_tools_with_letta(client, agent_id)
    log.info("tools_registered", tools=registered_tools)
    print(f"Tools registered: {len(registered_tools)}", flush=True)

    bot = create_bot(config, client, agent_id)
    log.info("discord_bot_created")
    print("Connecting to Discord...", flush=True)

    await bot.start(config.discord.bot_token)


def main():
    try:
        asyncio.run(run())

    except KeyboardInterrupt:
        log = get_logger("main")
        log.info("lares_shutdown", reason="keyboard_interrupt")
        print("\nLares shutting down gracefully...", flush=True)

    except Exception as e:
        log = get_logger("main")
        log.error("lares_startup_failed", error=str(e), error_type=type(e).__name__)
        print(f"Fatal error: {e}", flush=True, file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
