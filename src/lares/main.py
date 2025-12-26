"""Main entry point for Lares."""

import asyncio
import os
import sys

import structlog

from lares.config import load_config
from lares.discord_bot import create_bot
from lares.memory import create_letta_client, get_or_create_agent

# Configure structured logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.dev.ConsoleRenderer(),
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)

log = structlog.get_logger()


async def run() -> None:
    """Main async entry point."""
    log.info("starting_lares")

    # Load configuration
    try:
        config = load_config()
    except ValueError as e:
        log.error("configuration_error", error=str(e))
        print(f"Configuration error: {e}")
        print("Please copy .env.example to .env and fill in your credentials.")
        sys.exit(1)

    # Enable context monitoring if requested
    if os.getenv("LARES_CONTEXT_MONITORING", "false").lower() == "true":
        try:
            # Add project root to path to find tests directory
            project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
            if project_root not in sys.path:
                sys.path.insert(0, project_root)

            from tests.test_context_analysis import instrument_memory_module
            analyzer = instrument_memory_module()  # noqa: F841 - kept for future use
            log.info("context_monitoring_enabled")
        except ImportError as e:
            log.warning("context_monitoring_failed", error=str(e))
            print(f"Warning: Context monitoring requested but failed to load: {e}")

    # Initialize Letta client
    letta_client = create_letta_client(config)

    # Get or create the agent
    agent_id = await get_or_create_agent(letta_client, config)

    # Create and run Discord bot
    bot = create_bot(config, letta_client, agent_id)

    log.info("starting_discord_bot")
    await bot.start(config.discord.bot_token)


def main() -> None:
    """Synchronous entry point."""
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        log.info("shutdown_requested")
        print("\nLares is going to sleep. Goodbye!")


if __name__ == "__main__":
    main()
