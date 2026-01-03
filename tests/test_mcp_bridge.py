"""Tests for MCP approval bridge."""
import urllib.error
from unittest.mock import patch

import pytest

from lares.mcp_bridge import MCPApprovalBridge, PendingApproval


class TestPendingApproval:
    """Test the PendingApproval dataclass."""

    def test_create_pending_approval(self):
        """Test creating a pending approval."""
        pending = PendingApproval(
            approval_id="abc123",
            tool="test_tool",
            args={"key": "value"},
        )
        assert pending.approval_id == "abc123"
        assert pending.tool == "test_tool"
        assert pending.args == {"key": "value"}
        assert pending.message_id is None


class TestMCPApprovalBridge:
    """Test the MCPApprovalBridge class."""

    @pytest.fixture
    def bridge(self):
        """Create a bridge instance."""
        return MCPApprovalBridge()

    def test_format_approval_message(self, bridge):
        """Test formatting an approval message."""
        pending = PendingApproval(
            approval_id="test123",
            tool="run_shell_command",
            args={"command": "echo hello"},
        )
        msg = bridge.format_approval_message(pending)

        assert "test123" in msg
        assert "run_shell_command" in msg
        assert "echo hello" in msg
        assert "✅" in msg
        assert "❌" in msg

    def test_format_long_args_truncated(self, bridge):
        """Test that long args are truncated."""
        pending = PendingApproval(
            approval_id="test123",
            tool="write_file",
            args={"content": "x" * 1000},
        )
        msg = bridge.format_approval_message(pending)

        assert len(msg) < 1500  # Should be truncated
        assert "..." in msg

    def test_track_message(self, bridge):
        """Test tracking message to approval mapping."""
        pending = PendingApproval(
            approval_id="abc123",
            tool="test",
            args={},
        )
        bridge.pending["abc123"] = pending

        bridge.track_message("abc123", 999888777)

        assert bridge.pending["abc123"].message_id == 999888777
        assert bridge.message_to_approval[999888777] == "abc123"

    def test_health_check_returns_none_when_server_down(self, bridge):
        """Test health check returns None when MCP server not running."""
        # Mock urllib.request.urlopen to simulate connection error
        with patch(
            "urllib.request.urlopen",
            side_effect=urllib.error.URLError("Connection refused")
        ):
            result = bridge.health_check()
            assert result is None
