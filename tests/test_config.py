"""Tests for configuration loading."""

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from lares.config import load_config


def test_load_config_missing_discord_token():
    """Test that missing Discord token raises error."""
    with patch.dict(os.environ, {}, clear=True):
        with pytest.raises(ValueError, match="DISCORD_BOT_TOKEN"):
            load_config(env_path=Path("/nonexistent/.env"))


def test_load_config_missing_channel_id():
    """Test that missing channel ID raises error."""
    with patch.dict(os.environ, {"DISCORD_BOT_TOKEN": "token"}, clear=True):
        with pytest.raises(ValueError, match="DISCORD_CHANNEL_ID"):
            load_config(env_path=Path("/nonexistent/.env"))


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
    assert config.anthropic_api_key == "anthropic-key"
