"""Configuration management for Lares."""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass
class LettaConfig:
    """Letta service configuration."""

    api_key: str | None = None
    base_url: str | None = None  # For self-hosted: http://localhost:8283

    @property
    def is_self_hosted(self) -> bool:
        return self.base_url is not None


@dataclass
class DiscordConfig:
    """Discord bot configuration."""

    bot_token: str
    channel_id: int


@dataclass
class UserConfig:
    """Configuration about the user."""

    # IANA timezone name (e.g., "America/Los_Angeles", "Europe/Rome")
    timezone: str = "America/Los_Angeles"


@dataclass
class ToolsConfig:
    """Configuration for Lares's tools."""

    # Paths Lares can read/write (configurable for multi-project use)
    allowed_paths: list[str]

    # Files Lares should never read (secrets)
    blocked_files: list[str]

    # Commands Lares can run without approval (grows via approval workflow)
    command_allowlist: list[str]

    # Path to persist the command allowlist
    allowlist_file: Path


@dataclass
class LoggingConfig:
    """Logging configuration."""

    # Log level: DEBUG, INFO, WARNING, ERROR
    level: str = "INFO"

    # Directory for log files
    log_dir: str = "logs"

    # Maximum size of each log file in MB
    max_file_size_mb: int = 10

    # Number of backup log files to keep
    backup_count: int = 5

    # Whether to use JSON format (better for production)
    json_format: bool = False


@dataclass
class Config:
    """Main application configuration."""

    letta: LettaConfig
    discord: DiscordConfig
    tools: ToolsConfig
    logging: LoggingConfig
    user: UserConfig
    anthropic_api_key: str | None = None
    agent_id: str | None = None  # Persisted agent ID


def _load_allowlist(path: Path) -> list[str]:
    """Load command allowlist from file, creating with defaults if missing."""
    default_commands = [
        "git status",
        "git diff",
        "git log",
        "git add",
        "git commit",
        "git push",
        "git pull",
        "git branch",
        "git checkout",
        "pytest",
        "ruff check",
        "mypy",
        "pip list",
        "ls",
        "pwd",
        "cat",  # For reading files via shell if needed
    ]

    if path.exists():
        with open(path) as f:
            commands = [line.strip() for line in f if line.strip()]
            return commands if commands else default_commands
    else:
        # Create file with defaults
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            f.write("\n".join(default_commands) + "\n")
        return default_commands


def load_config(env_path: Path | None = None) -> Config:
    """Load configuration from environment variables."""
    if env_path:
        load_dotenv(env_path)
    else:
        load_dotenv()

    letta_config = LettaConfig(
        api_key=os.getenv("LETTA_API_KEY"),
        base_url=os.getenv("LETTA_BASE_URL"),
    )

    discord_token = os.getenv("DISCORD_BOT_TOKEN")
    if not discord_token:
        raise ValueError("DISCORD_BOT_TOKEN is required")

    channel_id_str = os.getenv("DISCORD_CHANNEL_ID")
    if not channel_id_str:
        raise ValueError("DISCORD_CHANNEL_ID is required")

    discord_config = DiscordConfig(
        bot_token=discord_token,
        channel_id=int(channel_id_str),
    )

    # User configuration
    user_config = UserConfig(
        timezone=os.getenv("USER_TIMEZONE", "America/Los_Angeles"),
    )

    # Tools configuration
    # Default to current working directory if not specified
    default_allowed_path = os.getcwd()
    allowed_paths_str = os.getenv("LARES_ALLOWED_PATHS", default_allowed_path)
    allowed_paths = [p.strip() for p in allowed_paths_str.split(":") if p.strip()]

    blocked_files_str = os.getenv(
        "LARES_BLOCKED_FILES", ".env,*.pem,*credential*,*secret*,*token*,id_rsa*"
    )
    blocked_files = [p.strip() for p in blocked_files_str.split(",") if p.strip()]

    # Default allowlist in .lares directory under current working directory
    default_allowlist = Path(os.getcwd()) / ".lares" / "command_allowlist.txt"
    allowlist_file = Path(os.getenv("LARES_ALLOWLIST_FILE", str(default_allowlist)))

    tools_config = ToolsConfig(
        allowed_paths=allowed_paths,
        blocked_files=blocked_files,
        command_allowlist=_load_allowlist(allowlist_file),
        allowlist_file=allowlist_file,
    )

    # Logging configuration
    logging_config = LoggingConfig(
        level=os.getenv("LARES_LOG_LEVEL", "INFO").upper(),
        log_dir=os.getenv("LARES_LOG_DIR", "logs"),
        max_file_size_mb=int(os.getenv("LARES_LOG_MAX_FILE_SIZE_MB", "10")),
        backup_count=int(os.getenv("LARES_LOG_BACKUP_COUNT", "5")),
        json_format=os.getenv("LARES_LOG_JSON_FORMAT", "false").lower() == "true",
    )

    return Config(
        letta=letta_config,
        discord=discord_config,
        tools=tools_config,
        logging=logging_config,
        user=user_config,
        anthropic_api_key=os.getenv("ANTHROPIC_API_KEY"),
        agent_id=os.getenv("LARES_AGENT_ID") or None,
    )
