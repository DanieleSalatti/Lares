"""SQLite implementation of MemoryProvider.

Pure SQLite-based memory storage - no external dependencies.
"""

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path

import aiosqlite
import structlog

from .memory import MemoryBlock, MemoryContext, MemoryProvider

log = structlog.get_logger()

DEFAULT_CHARS_PER_TOKEN = 4


class SqliteMemoryProvider(MemoryProvider):
    """Memory provider backed by SQLite.

    Stores messages, memory blocks, and summaries in a local SQLite database.
    """

    def __init__(
        self,
        db_path: str = "data/lares.db",
        base_instructions: str = "",
        chars_per_token: int = DEFAULT_CHARS_PER_TOKEN,
    ):
        """Initialize the SQLite memory provider.

        Args:
            db_path: Path to the SQLite database file
            base_instructions: System prompt / base instructions for context
            chars_per_token: Characters per token for estimation (default: 4)
        """
        self.db_path = Path(db_path)
        self.base_instructions = base_instructions
        self.chars_per_token = chars_per_token
        self._db: aiosqlite.Connection | None = None
        self._session_id: str = str(uuid.uuid4())

    async def initialize(self) -> None:
        """Initialize the database connection and ensure tables exist."""
        # Ensure data directory exists
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self._db = await aiosqlite.connect(self.db_path)
        self._db.row_factory = aiosqlite.Row

        # Create tables if they don't exist
        await self._create_tables()

        log.info(
            "sqlite_memory_provider_initialized",
            db_path=str(self.db_path),
            session_id=self._session_id,
        )

    async def shutdown(self) -> None:
        """Close the database connection."""
        if self._db:
            await self._db.close()
            self._db = None

    async def _create_tables(self) -> None:
        """Create tables if they don't exist."""
        if not self._db:
            raise RuntimeError("Provider not initialized")

        await self._db.executescript("""
            -- Conversation messages
            CREATE TABLE IF NOT EXISTS messages (
                id TEXT PRIMARY KEY,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                tool_calls TEXT,
                tool_call_id TEXT,
                session_id TEXT,
                token_count INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            -- Core memory blocks
            CREATE TABLE IF NOT EXISTS memory_blocks (
                label TEXT PRIMARY KEY,
                content TEXT NOT NULL,
                description TEXT,
                char_limit INTEGER DEFAULT 5000,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            -- Compacted conversation summaries
            CREATE TABLE IF NOT EXISTS summaries (
                id TEXT PRIMARY KEY,
                summary TEXT NOT NULL,
                start_message_id TEXT,
                end_message_id TEXT,
                token_count INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            -- Indexes
            CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id);
            CREATE INDEX IF NOT EXISTS idx_messages_created ON messages(created_at);
            CREATE INDEX IF NOT EXISTS idx_summaries_created ON summaries(created_at);
        """)
        await self._db.commit()

    async def get_context(self) -> MemoryContext:
        """Retrieve full context for LLM prompt building."""
        if not self._db:
            raise RuntimeError("Provider not initialized")

        # Get memory blocks
        blocks = await self._get_memory_blocks()

        # Get recent messages (limit for context window)
        messages = await self._get_recent_messages(limit=50)

        # Get summaries for older context
        summaries = await self._get_summaries()

        # Calculate estimated token count
        total_tokens = self._estimate_context_tokens(blocks, messages, summaries)

        return MemoryContext(
            base_instructions=self.base_instructions,
            blocks=blocks,
            messages=messages,
            tools=[],  # Tools are provided externally via MCP
            total_tokens=total_tokens,
        )

    def _estimate_tokens(self, text: str) -> int:
        """Estimate token count from text length."""
        if not text:
            return 0
        return len(text) // self.chars_per_token

    def _estimate_context_tokens(
        self,
        blocks: list[MemoryBlock],
        messages: list[dict],
        summaries: list[str],
    ) -> int:
        """Estimate total tokens in context."""
        total = self._estimate_tokens(self.base_instructions)
        for block in blocks:
            total += self._estimate_tokens(block.value)
            total += self._estimate_tokens(block.description)
        for msg in messages:
            total += self._estimate_tokens(msg.get("content", ""))
            total += 4  # role overhead
        for summary in summaries:
            total += self._estimate_tokens(summary)
        return total

    async def _get_memory_blocks(self) -> list[MemoryBlock]:
        """Fetch all memory blocks."""
        if not self._db:
            return []

        cursor = await self._db.execute(
            "SELECT label, content, description FROM memory_blocks ORDER BY label"
        )
        rows = await cursor.fetchall()

        return [
            MemoryBlock(
                label=row["label"],
                value=row["content"],
                description=row["description"] or "",
            )
            for row in rows
        ]

    async def _get_recent_messages(self, limit: int = 50) -> list[dict]:
        """Fetch recent messages for context."""
        if not self._db:
            return []

        cursor = await self._db.execute(
            """
            SELECT role, content, tool_calls, tool_call_id
            FROM messages
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (limit,),
        )
        rows = await cursor.fetchall()

        messages = []
        for row in reversed(rows):  # Oldest first
            msg = {"role": row["role"], "content": row["content"]}

            # Include tool call info if present
            if row["tool_calls"]:
                msg["tool_calls"] = json.loads(row["tool_calls"])
            if row["tool_call_id"]:
                msg["tool_call_id"] = row["tool_call_id"]

            messages.append(msg)

        return messages

    async def _get_summaries(self) -> list[str]:
        """Fetch conversation summaries."""
        if not self._db:
            return []

        cursor = await self._db.execute(
            "SELECT summary FROM summaries ORDER BY created_at ASC"
        )
        rows = await cursor.fetchall()
        return [row["summary"] for row in rows]

    async def add_message(
        self,
        role: str,
        content: str,
        tool_calls: list | None = None,
        tool_call_id: str | None = None,
    ) -> str:
        """Add a message to conversation history.

        Args:
            role: Message role (user/assistant/system/tool)
            content: Message content
            tool_calls: List of tool calls (for assistant messages)
            tool_call_id: Tool call ID (for tool response messages)

        Returns:
            The UUID of the created message
        """
        if not self._db:
            raise RuntimeError("Provider not initialized")

        message_id = str(uuid.uuid4())

        await self._db.execute(
            """
            INSERT INTO messages
            (id, role, content, tool_calls, tool_call_id, session_id, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                message_id,
                role,
                content,
                json.dumps(tool_calls) if tool_calls else None,
                tool_call_id,
                self._session_id,
                datetime.now(tz=UTC).isoformat(),
            ),
        )
        await self._db.commit()

        log.debug("message_added", message_id=message_id, role=role)
        return message_id

    async def update_block(self, label: str, value: str) -> None:
        """Update a memory block's value (upsert)."""
        if not self._db:
            raise RuntimeError("Provider not initialized")

        await self._db.execute(
            """
            INSERT INTO memory_blocks (label, content, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(label) DO UPDATE SET
                content = excluded.content,
                updated_at = excluded.updated_at
            """,
            (label, value, datetime.now(tz=UTC).isoformat()),
        )
        await self._db.commit()

        log.info("memory_block_updated", label=label)

    async def search(self, query: str, limit: int = 10) -> list[dict]:
        """Search memory for relevant content.

        Note: This is basic text search. For semantic search,
        we'd need to add embeddings (future enhancement).
        """
        if not self._db:
            raise RuntimeError("Provider not initialized")

        # Simple LIKE search for now
        pattern = f"%{query}%"

        cursor = await self._db.execute(
            """
            SELECT id, role, content, created_at
            FROM messages
            WHERE content LIKE ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (pattern, limit),
        )
        rows = await cursor.fetchall()

        return [
            {
                "id": row["id"],
                "role": row["role"],
                "content": row["content"],
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    async def add_summary(
        self,
        summary: str,
        start_message_id: str | None = None,
        end_message_id: str | None = None,
    ) -> str:
        """Add a compacted summary.

        Args:
            summary: The summary text
            start_message_id: UUID of first message in summarized range
            end_message_id: UUID of last message in summarized range

        Returns:
            The UUID of the created summary
        """
        if not self._db:
            raise RuntimeError("Provider not initialized")

        summary_id = str(uuid.uuid4())

        await self._db.execute(
            """
            INSERT INTO summaries (id, summary, start_message_id, end_message_id, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                summary_id,
                summary,
                start_message_id,
                end_message_id,
                datetime.now(tz=UTC).isoformat(),
            ),
        )
        await self._db.commit()

        log.info("summary_added", summary_id=summary_id)
        return summary_id

    async def get_message_count(self) -> int:
        """Get total message count (for compaction decisions)."""
        if not self._db:
            return 0

        cursor = await self._db.execute("SELECT COUNT(*) as count FROM messages")
        row = await cursor.fetchone()
        return row["count"] if row else 0

    async def delete_messages_before(self, message_id: str) -> int:
        """Delete messages before a given ID (after compaction).

        Returns number of deleted messages.
        """
        if not self._db:
            return 0

        # Get the created_at of the reference message
        cursor = await self._db.execute(
            "SELECT created_at FROM messages WHERE id = ?", (message_id,)
        )
        row = await cursor.fetchone()
        if not row:
            return 0

        reference_time = row["created_at"]

        cursor = await self._db.execute(
            "DELETE FROM messages WHERE created_at < ?", (reference_time,)
        )
        await self._db.commit()

        deleted = cursor.rowcount
        log.info("messages_deleted", count=deleted, before=reference_time)
        return deleted
