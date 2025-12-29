"""
Approval queue system for MCP server.
Uses SQLite for persistence across restarts.
"""

import json
import sqlite3
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# Default database location
DEFAULT_DB_PATH = Path(__file__).parent.parent.parent / "data" / "approvals.db"


def extract_command_pattern(command: str) -> str:
    """
    Extract a reusable pattern from a command.

    Strategy: Use the base command (first word, or full path basename).
    This allows "beans list" to match all "beans *" commands.

    Examples:
        "beans list" -> "beans"
        "/home/daniele/go/bin/beans list" -> "beans"
        "curl http://localhost:8765/health" -> "curl"
        "python3 -c 'print(1)'" -> "python3"
    """
    # Split on whitespace
    parts = command.strip().split()
    if not parts:
        return command

    first = parts[0]

    # If it's a path, extract the basename
    if "/" in first:
        first = Path(first).name

    return first


def command_matches_pattern(command: str, pattern: str) -> bool:
    """Check if a command matches a remembered pattern."""
    cmd_pattern = extract_command_pattern(command)
    return cmd_pattern.lower() == pattern.lower()


class ApprovalQueue:
    """SQLite-backed approval queue for sensitive operations."""

    def __init__(self, db_path: Path | str | None = None):
        self.db_path = Path(db_path) if db_path else DEFAULT_DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        """Initialize the database schema."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS approvals (
                    id TEXT PRIMARY KEY,
                    tool TEXT NOT NULL,
                    args TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    result TEXT,
                    created_at TEXT NOT NULL,
                    resolved_at TEXT
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_status ON approvals(status)
            """)
            # New table for remembered command patterns
            conn.execute("""
                CREATE TABLE IF NOT EXISTS remembered_commands (
                    pattern TEXT PRIMARY KEY,
                    original_command TEXT NOT NULL,
                    approved_by TEXT,
                    created_at TEXT NOT NULL
                )
            """)
            conn.commit()

    def submit(self, tool: str, args: dict[str, Any]) -> str:
        """Submit an operation for approval. Returns approval ID."""
        approval_id = str(uuid.uuid4())[:8]
        now = datetime.now(UTC).isoformat()

        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """INSERT INTO approvals (id, tool, args, status, created_at)
                   VALUES (?, ?, ?, 'pending', ?)""",
                (approval_id, tool, json.dumps(args), now),
            )
            conn.commit()

        return approval_id

    def get_pending(self) -> list[dict]:
        """Get all pending approvals."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT * FROM approvals WHERE status = 'pending' ORDER BY created_at"
            )
            return [dict(row) for row in cursor.fetchall()]

    def get(self, approval_id: str) -> dict | None:
        """Get a specific approval by ID."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT * FROM approvals WHERE id = ?",
                (approval_id,),
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    def approve(self, approval_id: str) -> bool:
        """Mark an approval as approved."""
        now = datetime.now(UTC).isoformat()
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """UPDATE approvals SET status = 'approved', resolved_at = ?
                   WHERE id = ? AND status = 'pending'""",
                (now, approval_id),
            )
            conn.commit()
            return cursor.rowcount > 0

    def deny(self, approval_id: str) -> bool:
        """Mark an approval as denied."""
        now = datetime.now(UTC).isoformat()
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """UPDATE approvals SET status = 'denied', resolved_at = ?
                   WHERE id = ? AND status = 'pending'""",
                (now, approval_id),
            )
            conn.commit()
            return cursor.rowcount > 0

    def set_result(self, approval_id: str, result: str):
        """Store the result of an executed operation."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE approvals SET result = ? WHERE id = ?",
                (result, approval_id),
            )
            conn.commit()

    def cleanup_old(self, days: int = 7):
        """Remove resolved approvals older than specified days."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """DELETE FROM approvals
                   WHERE status != 'pending'
                   AND datetime(resolved_at) < datetime('now', ?)""",
                (f"-{days} days",),
            )
            conn.commit()

    # === REMEMBERED COMMANDS ===

    def add_remembered_command(self, command: str, approved_by: str | None = None) -> str:
        """
        Add a command pattern to the remembered list.
        Returns the pattern that was added.
        """
        pattern = extract_command_pattern(command)
        now = datetime.now(UTC).isoformat()

        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """INSERT OR REPLACE INTO remembered_commands
                   (pattern, original_command, approved_by, created_at)
                   VALUES (?, ?, ?, ?)""",
                (pattern, command, approved_by, now),
            )
            conn.commit()

        return pattern

    def is_command_remembered(self, command: str) -> bool:
        """Check if a command matches any remembered pattern."""
        pattern = extract_command_pattern(command)

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT 1 FROM remembered_commands WHERE pattern = ?",
                (pattern,),
            )
            return cursor.fetchone() is not None

    def get_remembered_commands(self) -> list[dict]:
        """Get all remembered command patterns."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("SELECT * FROM remembered_commands ORDER BY created_at")
            return [dict(row) for row in cursor.fetchall()]

    def remove_remembered_command(self, pattern: str) -> bool:
        """Remove a remembered command pattern."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "DELETE FROM remembered_commands WHERE pattern = ?",
                (pattern,),
            )
            conn.commit()
            return cursor.rowcount > 0


# Singleton instance
_queue: ApprovalQueue | None = None


def get_queue(db_path: Path | str | None = None) -> ApprovalQueue:
    """Get or create the approval queue singleton."""
    global _queue
    if _queue is None:
        _queue = ApprovalQueue(db_path)
    return _queue
