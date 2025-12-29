"""Tests for MCP approval queue."""

import tempfile
from pathlib import Path

import pytest

from lares.mcp_approval import ApprovalQueue


@pytest.fixture
def temp_db():
    """Create a temporary database file."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        yield Path(f.name)
    Path(f.name).unlink(missing_ok=True)


@pytest.fixture
def queue(temp_db):
    """Create an approval queue with temp database."""
    return ApprovalQueue(temp_db)


class TestApprovalQueue:
    """Test the ApprovalQueue class."""

    def test_submit_creates_pending_approval(self, queue):
        """Test that submit creates a pending approval."""
        aid = queue.submit("test_tool", {"arg": "value"})
        assert aid is not None
        assert len(aid) == 8  # UUID prefix

        item = queue.get(aid)
        assert item is not None
        assert item["tool"] == "test_tool"
        assert item["status"] == "pending"

    def test_get_pending_returns_only_pending(self, queue):
        """Test that get_pending only returns pending items."""
        aid1 = queue.submit("tool1", {})
        aid2 = queue.submit("tool2", {})

        pending = queue.get_pending()
        assert len(pending) == 2

        queue.approve(aid1)
        pending = queue.get_pending()
        assert len(pending) == 1
        assert pending[0]["id"] == aid2

    def test_approve_updates_status(self, queue):
        """Test that approve updates status correctly."""
        aid = queue.submit("test_tool", {})

        result = queue.approve(aid)
        assert result is True

        item = queue.get(aid)
        assert item["status"] == "approved"
        assert item["resolved_at"] is not None

    def test_deny_updates_status(self, queue):
        """Test that deny updates status correctly."""
        aid = queue.submit("test_tool", {})

        result = queue.deny(aid)
        assert result is True

        item = queue.get(aid)
        assert item["status"] == "denied"
        assert item["resolved_at"] is not None

    def test_approve_already_resolved_fails(self, queue):
        """Test that approving already resolved item fails."""
        aid = queue.submit("test_tool", {})
        queue.approve(aid)

        # Try to approve again
        result = queue.approve(aid)
        assert result is False

    def test_set_result_stores_result(self, queue):
        """Test that set_result stores the execution result."""
        aid = queue.submit("test_tool", {})
        queue.approve(aid)
        queue.set_result(aid, "execution output here")

        item = queue.get(aid)
        assert item["result"] == "execution output here"

    def test_get_nonexistent_returns_none(self, queue):
        """Test that getting nonexistent ID returns None."""
        item = queue.get("nonexistent")
        assert item is None

    def test_persistence_across_instances(self, temp_db):
        """Test that data persists across queue instances."""
        queue1 = ApprovalQueue(temp_db)
        aid = queue1.submit("persistent_tool", {"key": "value"})

        # Create new instance with same DB
        queue2 = ApprovalQueue(temp_db)
        item = queue2.get(aid)

        assert item is not None
        assert item["tool"] == "persistent_tool"


class TestRememberedCommands:
    """Tests for the remembered commands functionality."""

    def test_add_remembered_command(self, queue: ApprovalQueue):
        """Test adding a command to remembered patterns."""
        pattern = queue.add_remembered_command("beans list --all", approved_by="daniele")
        assert pattern == "beans"

    def test_extract_pattern_simple_command(self, queue: ApprovalQueue):
        """Test pattern extraction from simple commands."""
        queue.add_remembered_command("curl http://localhost:8765/health")
        assert queue.is_command_remembered("curl http://other.server/api")

    def test_extract_pattern_full_path(self, queue: ApprovalQueue):
        """Test pattern extraction from full path commands."""
        queue.add_remembered_command("/home/daniele/go/bin/beans list")
        assert queue.is_command_remembered("beans status")
        assert queue.is_command_remembered("/home/daniele/go/bin/beans other")

    def test_is_command_remembered_false(self, queue: ApprovalQueue):
        """Test that non-remembered commands return False."""
        assert not queue.is_command_remembered("unknown_command arg1")

    def test_get_remembered_commands(self, queue: ApprovalQueue):
        """Test listing remembered commands."""
        queue.add_remembered_command("pip install something", approved_by="daniele")
        queue.add_remembered_command("npm run build", approved_by="daniele")
        
        patterns = queue.get_remembered_commands()
        assert len(patterns) == 2
        pattern_names = [p["pattern"] for p in patterns]
        assert "pip" in pattern_names
        assert "npm" in pattern_names

    def test_remove_remembered_command(self, queue: ApprovalQueue):
        """Test removing a remembered pattern."""
        queue.add_remembered_command("docker compose up")
        assert queue.is_command_remembered("docker ps")
        
        removed = queue.remove_remembered_command("docker")
        assert removed
        assert not queue.is_command_remembered("docker ps")
