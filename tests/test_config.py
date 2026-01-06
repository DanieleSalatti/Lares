"""Tests for configuration loading."""

import os
from pathlib import Path
from unittest.mock import patch

from lares.config import load_config, load_discord_config


def test_load_discord_config_missing_values():
    """Test that missing Discord values result in None (graceful handling)."""
    with patch.dict(os.environ, {}, clear=True):
        config = load_discord_config()
        assert config.bot_token is None
        assert config.channel_id is None
        assert config.enabled is False


def test_load_discord_config_partial():
    """Test that partial Discord config is handled gracefully."""
    with patch.dict(os.environ, {"DISCORD_BOT_TOKEN": "token"}, clear=True):
        config = load_discord_config()
        assert config.bot_token == "token"
        assert config.channel_id is None
        assert config.enabled is False


def test_load_config_without_discord():
    """Test that load_config works without Discord credentials."""
    with patch.dict(os.environ, {}, clear=True):
        config = load_config(env_path=Path("/nonexistent/.env"))
        assert config.discord.bot_token is None
        assert config.discord.channel_id is None
        assert config.discord.enabled is False


def test_load_config_success():
    """Test successful config loading."""
    env = {
        "DISCORD_BOT_TOKEN": "test-token",
        "DISCORD_CHANNEL_ID": "123456789",
        "ANTHROPIC_API_KEY": "anthropic-key",
    }
    with patch.dict(os.environ, env, clear=True):
        config = load_config(env_path=Path("/nonexistent/.env"))

    assert config.discord.bot_token == "test-token"
    assert config.discord.channel_id == 123456789
    assert config.discord.enabled is True
    assert config.anthropic_api_key == "anthropic-key"
