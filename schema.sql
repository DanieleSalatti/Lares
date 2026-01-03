-- Lares Database Schema
-- Database: data/lares.db
-- Initialize: sqlite3 data/lares.db < schema.sql

-- Approval queue
CREATE TABLE IF NOT EXISTS approvals (
    id TEXT PRIMARY KEY,              -- UUID
    tool_name TEXT NOT NULL,
    arguments TEXT NOT NULL,          -- JSON
    status TEXT DEFAULT 'pending',    -- pending/approved/denied
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    resolved_at TIMESTAMP,
    result TEXT
);

-- Conversation messages
CREATE TABLE IF NOT EXISTS messages (
    id TEXT PRIMARY KEY,              -- UUID
    role TEXT NOT NULL,               -- user/assistant/system/tool
    content TEXT NOT NULL,
    tool_calls TEXT,                  -- JSON array if assistant called tools
    tool_call_id TEXT,                -- UUID if this is a tool response
    session_id TEXT,                  -- UUID to group related conversations
    token_count INTEGER,              -- for context window management
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Core memory blocks (persona, human, state, ideas, etc.)
CREATE TABLE IF NOT EXISTS memory_blocks (
    label TEXT PRIMARY KEY,           -- 'persona', 'human', 'state', 'ideas'
    content TEXT NOT NULL,
    description TEXT,
    char_limit INTEGER DEFAULT 5000,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Compacted conversation summaries
CREATE TABLE IF NOT EXISTS summaries (
    id TEXT PRIMARY KEY,              -- UUID
    summary TEXT NOT NULL,
    start_message_id TEXT,            -- UUID of first message in range
    end_message_id TEXT,              -- UUID of last message in range
    token_count INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for efficient queries
CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id);
CREATE INDEX IF NOT EXISTS idx_messages_created ON messages(created_at);
CREATE INDEX IF NOT EXISTS idx_approvals_status ON approvals(status);
CREATE INDEX IF NOT EXISTS idx_summaries_created ON summaries(created_at);
