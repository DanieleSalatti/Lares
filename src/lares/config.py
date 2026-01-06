"""Configuration management for Lares."""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


@dataclass
class DiscordConfig:
    """Discord bot configuration."""

    bot_token: str | None
    channel_id: int | None

    @property
    def enabled(self) -> bool:
        """Check if Discord is configured and enabled."""
        return bool(self.bot_token and self.channel_id)


@dataclass
class UserConfig:
    """Configuration about the user."""

    timezone: str = "America/Los_Angeles"


@dataclass
class ToolsConfig:
    """Configuration for Lares's tools."""

    allowed_paths: list[str]
    blocked_files: list[str]
    command_allowlist: list[str]
    allowlist_file: Path


@dataclass
class LoggingConfig:
    """Logging configuration."""

    level: str = "INFO"
    log_dir: str = "logs"
    max_file_size_mb: int = 10
    backup_count: int = 5
    json_format: bool = False


@dataclass
class Config:
    """Main application configuration."""

    discord: DiscordConfig
    tools: ToolsConfig
    logging: LoggingConfig
    user: UserConfig
    anthropic_api_key: str | None = None


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
        "cat",
    ]

    if path.exists():
        with open(path) as f:
            commands = [line.strip() for line in f if line.strip()]
            return commands if commands else default_commands
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            f.write("\n".join(default_commands) + "\n")
        return default_commands


def load_config(env_path: Path | None = None) -> Config:
    """Load configuration from environment variables."""
    if env_path:
        load_dotenv(env_path, override=True)

    discord_config = load_discord_config()

    user_config = UserConfig(
        timezone=os.getenv("USER_TIMEZONE", "America/Los_Angeles"),
    )

    default_allowed_path = os.getcwd()
    allowed_paths_str = os.getenv("LARES_ALLOWED_PATHS", default_allowed_path)
    allowed_paths = [p.strip() for p in allowed_paths_str.split(":") if p.strip()]

    blocked_files_str = os.getenv(
        "LARES_BLOCKED_FILES", ".env,*.pem,*credential*,*secret*,*token*,id_rsa*"
    )
    blocked_files = [p.strip() for p in blocked_files_str.split(",") if p.strip()]

    default_allowlist = Path(os.getcwd()) / ".lares" / "command_allowlist.txt"
    allowlist_file = Path(os.getenv("LARES_ALLOWLIST_FILE", str(default_allowlist)))

    tools_config = ToolsConfig(
        allowed_paths=allowed_paths,
        blocked_files=blocked_files,
        command_allowlist=_load_allowlist(allowlist_file),
        allowlist_file=allowlist_file,
    )

    logging_config = LoggingConfig(
        level=os.getenv("LARES_LOG_LEVEL", "INFO").upper(),
        log_dir=os.getenv("LARES_LOG_DIR", "logs"),
        max_file_size_mb=int(os.getenv("LARES_LOG_MAX_FILE_SIZE_MB", "10")),
        backup_count=int(os.getenv("LARES_LOG_BACKUP_COUNT", "5")),
        json_format=os.getenv("LARES_LOG_JSON_FORMAT", "false").lower() == "true",
    )

    return Config(
        discord=discord_config,
        tools=tools_config,
        logging=logging_config,
        user=user_config,
        anthropic_api_key=os.getenv("ANTHROPIC_API_KEY"),
    )


@dataclass
class MemoryConfig:
    """Memory provider configuration."""

    sqlite_path: str = "data/lares.db"
    context_limit: int = 50_000
    compact_threshold: float = 0.70
    target_after_compact: float = 0.25
    chars_per_token: int = 4


@dataclass
class PathsConfig:
    """Path configuration for Lares."""

    project_path: Path
    obsidian_vault: Path
    allowed_directories: list[Path]
    approval_db: Path


@dataclass
class BlueskyConfig:
    """BlueSky API configuration."""

    handle: str | None
    app_password: str | None
    public_api: str = "https://public.api.bsky.app/xrpc"
    auth_api: str = "https://bsky.social/xrpc"

    @property
    def enabled(self) -> bool:
        """Check if BlueSky auth is configured."""
        return bool(self.handle and self.app_password)


@dataclass
class McpConfig:
    """MCP server configuration."""

    host: str = "0.0.0.0"
    port: int = 8765
    shell_require_all_approval: bool = False


def load_memory_config() -> MemoryConfig:
    """Load memory configuration from environment variables."""
    return MemoryConfig(
        sqlite_path=os.getenv("SQLITE_DB_PATH", "data/lares.db"),
        context_limit=int(os.getenv("LARES_CONTEXT_WINDOW_LIMIT", "50000")),
        compact_threshold=float(os.getenv("COMPACT_THRESHOLD", "0.70")),
        target_after_compact=float(os.getenv("TARGET_AFTER_COMPACT", "0.25")),
        chars_per_token=int(os.getenv("CHARS_PER_TOKEN", "4")),
    )


def load_discord_config() -> DiscordConfig:
    """Load Discord configuration (gracefully handles missing values)."""
    bot_token = os.getenv("DISCORD_BOT_TOKEN") or None
    channel_id_str = os.getenv("DISCORD_CHANNEL_ID")
    channel_id = int(channel_id_str) if channel_id_str else None
    return DiscordConfig(bot_token=bot_token, channel_id=channel_id)


def load_paths_config() -> PathsConfig:
    """Load paths configuration from environment variables."""
    project_path = Path(
        os.getenv("LARES_PROJECT_PATH", "/home/daniele/workspace/lares")
    )
    obsidian_vault = Path(
        os.getenv("OBSIDIAN_VAULT_PATH", "/home/daniele/workspace/gitlab/daniele/appunti")
    )
    approval_db = Path(
        os.getenv("LARES_APPROVAL_DB", "/home/daniele/workspace/lares/data/approvals.db")
    )

    allowed_paths_str = os.getenv("LARES_ALLOWED_PATHS", "")
    if allowed_paths_str:
        allowed_directories = [
            Path(p.strip()) for p in allowed_paths_str.split(":") if p.strip()
        ]
    else:
        allowed_directories = [project_path, obsidian_vault]

    return PathsConfig(
        project_path=project_path,
        obsidian_vault=obsidian_vault,
        allowed_directories=allowed_directories,
        approval_db=approval_db,
    )


def load_bluesky_config() -> BlueskyConfig:
    """Load BlueSky configuration from environment variables."""
    return BlueskyConfig(
        handle=os.getenv("BLUESKY_HANDLE") or None,
        app_password=os.getenv("BLUESKY_APP_PASSWORD") or None,
    )


def load_mcp_config() -> McpConfig:
    """Load MCP server configuration from environment variables."""
    return McpConfig(
        host=os.getenv("MCP_HOST", "0.0.0.0"),
        port=int(os.getenv("MCP_PORT", "8765")),
        shell_require_all_approval=os.getenv(
            "MCP_SHELL_REQUIRE_APPROVAL", ""
        ).lower() == "true",
    )
