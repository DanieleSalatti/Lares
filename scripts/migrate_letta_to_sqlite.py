#!/usr/bin/env python3
"""Migrate memory blocks and messages from Letta to SQLite.

Standalone script - no lares imports to avoid approval queue triggers.

Usage:
    python scripts/migrate_letta_to_sqlite.py

Requires environment variables (set in .env or exported):
    LETTA_BASE_URL - Letta server URL
    LARES_AGENT_ID - Letta agent ID
    SQLITE_DB_PATH - Target SQLite database path (default: data/lares.db)
"""

import asyncio
import os
import sqlite3
import sys
import uuid
from datetime import datetime, timezone

import httpx

# Load .env file manually
env_path = os.path.join(os.path.dirname(__file__), '..', '.env')
if os.path.exists(env_path):
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                os.environ.setdefault(key.strip(), value.strip())


# SQLite schema - MUST match SqliteMemoryProvider exactly!
SCHEMA = """
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
"""


async def get_letta_blocks(base_url: str, agent_id: str) -> list[dict]:
    """Fetch memory blocks directly from Letta API."""
    async with httpx.AsyncClient(base_url=base_url, timeout=30.0) as client:
        url = f"/v1/agents/{agent_id}/core-memory"
        response = await client.get(url)
        response.raise_for_status()
        data = response.json()
        return data.get("blocks", [])


async def get_letta_context(base_url: str, agent_id: str) -> dict:
    """Fetch agent context from Letta API."""
    async with httpx.AsyncClient(base_url=base_url, timeout=30.0) as client:
        url = f"/v1/agents/{agent_id}/context"
        response = await client.get(url)
        response.raise_for_status()
        return response.json()


async def get_letta_messages(base_url: str, agent_id: str, limit: int = 1000) -> list[dict]:
    """Fetch messages from Letta API.
    
    Uses the agent's message history endpoint.
    """
    async with httpx.AsyncClient(base_url=base_url, timeout=60.0) as client:
        # Try the messages endpoint - Letta may paginate
        url = f"/v1/agents/{agent_id}/messages"
        params = {"limit": limit}
        response = await client.get(url, params=params)
        response.raise_for_status()
        return response.json()


def init_sqlite(db_path: str) -> sqlite3.Connection:
    """Initialize SQLite database with schema."""
    os.makedirs(os.path.dirname(db_path) or '.', exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.executescript(SCHEMA)
    conn.commit()
    return conn


def upsert_block(conn: sqlite3.Connection, label: str, value: str, description: str = ""):
    """Insert or update a memory block.
    
    Uses label as primary key (matching SqliteMemoryProvider).
    """
    now = datetime.now(timezone.utc).isoformat()
    
    # UPSERT using INSERT OR REPLACE (label is PK)
    conn.execute(
        """
        INSERT OR REPLACE INTO memory_blocks (label, content, description, updated_at)
        VALUES (?, ?, ?, ?)
        """,
        (label, value, description, now)
    )
    conn.commit()


def insert_message(conn: sqlite3.Connection, role: str, content: str, 
                   created_at: str | None = None, session_id: str = "migrated"):
    """Insert a message into SQLite."""
    msg_id = str(uuid.uuid4())
    timestamp = created_at or datetime.now(timezone.utc).isoformat()
    
    conn.execute(
        """
        INSERT OR IGNORE INTO messages (id, role, content, session_id, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (msg_id, role, content, session_id, timestamp)
    )


def convert_letta_messages(letta_messages: list) -> list[dict]:
    """Convert Letta message format to simple role/content format.
    
    Handles various Letta message formats and extracts text content.
    """
    messages = []
    
    for msg in letta_messages:
        role = msg.get("role", "")
        content = msg.get("content", "")
        created_at = msg.get("created_at") or msg.get("date")
        
        # Handle content that may be a list of blocks
        if isinstance(content, list):
            texts = []
            for block in content:
                if isinstance(block, dict):
                    if block.get("type") == "text":
                        texts.append(block.get("text", ""))
                    elif "text" in block:
                        texts.append(block["text"])
                elif isinstance(block, str):
                    texts.append(block)
            content = "".join(texts)
        
        # Only include user and assistant text messages
        if role in ("user", "assistant") and content and content.strip():
            messages.append({
                "role": role,
                "content": content.strip(),
                "created_at": created_at,
            })
    
    return messages


async def main():
    # Get config from env
    letta_url = os.getenv("LETTA_BASE_URL")
    agent_id = os.getenv("LARES_AGENT_ID")
    sqlite_path = os.getenv("SQLITE_DB_PATH", "data/lares.db")
    migrate_messages = os.getenv("MIGRATE_MESSAGES", "true").lower() == "true"
    
    if not letta_url or not agent_id:
        print("Error: LETTA_BASE_URL and LARES_AGENT_ID required")
        print(f"  LETTA_BASE_URL = {letta_url}")
        print(f"  LARES_AGENT_ID = {agent_id}")
        sys.exit(1)
    
    print(f"Migrating from Letta ({letta_url}) agent {agent_id}")
    print(f"Target SQLite: {sqlite_path}")
    print(f"Migrate messages: {migrate_messages}")
    print()
    
    # Get blocks directly from Letta API
    print("Fetching memory blocks from Letta...")
    blocks = await get_letta_blocks(letta_url, agent_id)
    
    print(f"Found {len(blocks)} memory blocks:")
    for block in blocks:
        label = block.get("label", "unknown")
        value = block.get("value", "")
        print(f"  - {label}: {len(value)} chars")
    
    # Get context for base instructions
    print("\nFetching agent context...")
    context = await get_letta_context(letta_url, agent_id)
    base_instructions = context.get("system_prompt", "")
    print(f"Base instructions: {len(base_instructions)} chars")
    
    # Get messages if requested
    raw_messages = []
    if migrate_messages:
        print("\nFetching message history...")
        try:
            raw_messages = await get_letta_messages(letta_url, agent_id)
            print(f"Found {len(raw_messages)} raw messages")
        except Exception as e:
            print(f"Warning: Could not fetch messages: {e}")
            print("Continuing without message migration...")
    
    print()
    
    # Initialize SQLite
    print("Initializing SQLite database...")
    conn = init_sqlite(sqlite_path)
    
    # Store base instructions as a special block
    upsert_block(conn, "_base_instructions", base_instructions, "System base instructions")
    print("  ✓ _base_instructions")
    
    # Migrate blocks
    print("\nMigrating memory blocks...")
    for block in blocks:
        label = block.get("label")
        value = block.get("value", "")
        description = block.get("description", "")
        
        if label:
            upsert_block(conn, label, value, description)
            print(f"  ✓ {label}")
    
    # Migrate messages
    if migrate_messages and raw_messages:
        print("\nMigrating message history...")
        converted = convert_letta_messages(raw_messages)
        print(f"  Converted {len(converted)} user/assistant messages")
        
        for msg in converted:
            insert_message(
                conn, 
                msg["role"], 
                msg["content"], 
                msg.get("created_at"),
                session_id="migrated"
            )
        conn.commit()
        print(f"  ✓ Inserted {len(converted)} messages")
    elif not migrate_messages:
        print("\nSkipping message history (MIGRATE_MESSAGES=false)")
    else:
        print("\nNo messages to migrate")
    
    # Verify
    print("\nVerifying migration...")
    
    cursor = conn.execute("SELECT label, LENGTH(content) FROM memory_blocks ORDER BY label")
    rows = cursor.fetchall()
    print(f"  Blocks in SQLite: {len(rows)}")
    total_chars = 0
    for label, length in rows:
        print(f"    - {label}: {length} chars")
        total_chars += length
    print(f"  Total: {total_chars} chars")
    
    cursor = conn.execute("SELECT COUNT(*) FROM messages")
    msg_count = cursor.fetchone()[0]
    print(f"  Messages in SQLite: {msg_count}")
    
    if msg_count > 0:
        cursor = conn.execute(
            "SELECT role, COUNT(*) FROM messages GROUP BY role"
        )
        for role, count in cursor.fetchall():
            print(f"    - {role}: {count}")
    
    conn.close()
    
    print("\n✅ Migration complete!")
    print(f"\nTo switch to SQLite mode, set in .env:")
    print(f"  USE_DIRECT_LLM=true")


if __name__ == "__main__":
    asyncio.run(main())
