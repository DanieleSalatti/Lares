"""Memory compaction service.

Summarizes old messages to keep context within token limits.
"""

import structlog

from .config import MemoryConfig, load_memory_config
from .providers.llm import LLMProvider
from .providers.sqlite import SqliteMemoryProvider

log = structlog.get_logger()

_config: MemoryConfig | None = None


def _get_config() -> MemoryConfig:
    global _config
    if _config is None:
        _config = load_memory_config()
    return _config


def estimate_tokens(text: str) -> int:
    """Estimate token count from text.

    Uses a conservative chars-per-token ratio.
    For more accuracy, could use tiktoken or Anthropic's API.
    """
    return len(text) // _get_config().chars_per_token


def estimate_context_tokens(
    base_instructions: str,
    memory_blocks: list,
    summaries: list[str],
    messages: list[dict],
) -> int:
    """Estimate total tokens for a context window."""
    total_chars = len(base_instructions)

    for block in memory_blocks:
        total_chars += len(block.value) + len(block.label) + len(block.description)

    for summary in summaries:
        total_chars += len(summary)

    for msg in messages:
        total_chars += len(msg.get("content", ""))
        if "tool_calls" in msg:
            total_chars += len(str(msg["tool_calls"]))

    return total_chars // _get_config().chars_per_token


class CompactionService:
    """Handles memory compaction via LLM summarization."""

    SUMMARIZE_PROMPT = """Summarize the following conversation history, preserving:
- Key facts and decisions made
- Important context for future conversations
- User preferences or corrections mentioned
- Any ongoing tasks or commitments

Be concise but don't lose critical information. Write in third person.

Conversation to summarize:
{messages}

Summary:"""

    def __init__(
        self,
        memory: SqliteMemoryProvider,
        llm: LLMProvider,
        context_limit: int | None = None,
        compact_threshold: float | None = None,
        target_ratio: float | None = None,
    ):
        """Initialize the compaction service.

        Args:
            memory: The SQLite memory provider to compact
            llm: LLM provider for generating summaries
            context_limit: Max context window size in tokens
            compact_threshold: Trigger compaction at this % of limit
            target_ratio: Target this % of limit after compaction
        """
        config = _get_config()
        self.memory = memory
        self.llm = llm
        self.context_limit = context_limit if context_limit is not None else config.context_limit
        self.compact_threshold = compact_threshold if compact_threshold is not None else config.compact_threshold
        self.target_ratio = target_ratio if target_ratio is not None else config.target_after_compact

    async def needs_compaction(self) -> bool:
        """Check if compaction is needed based on current context size."""
        context = await self.memory.get_context()

        # Get summaries for full picture
        summaries = await self.memory._get_summaries()

        current_tokens = estimate_context_tokens(
            context.base_instructions,
            context.blocks,
            summaries,
            context.messages,
        )

        threshold_tokens = int(self.context_limit * self.compact_threshold)
        needs_it = current_tokens >= threshold_tokens

        log.info(
            "compaction_check",
            current_tokens=current_tokens,
            threshold_tokens=threshold_tokens,
            needs_compaction=needs_it,
        )

        return needs_it

    async def compact(self) -> dict:
        """Run compaction: summarize old messages, delete them.

        Returns:
            Dict with compaction stats
        """
        log.info("compaction_starting")

        # Get current state
        context = await self.memory.get_context()
        messages = context.messages

        if len(messages) < 10:
            log.info("compaction_skipped", reason="too_few_messages")
            return {"skipped": True, "reason": "too_few_messages"}

        # Calculate how many messages to summarize
        # Keep recent messages, summarize the rest
        target_tokens = int(self.context_limit * self.target_ratio)

        # Work backwards from most recent, keep until we hit target
        kept_messages = []
        kept_tokens = 0

        for msg in reversed(messages):
            msg_tokens = estimate_tokens(msg.get("content", ""))
            if kept_tokens + msg_tokens > target_tokens:
                break
            kept_messages.insert(0, msg)
            kept_tokens += msg_tokens

        # Messages to summarize (the ones we didn't keep)
        to_summarize = messages[:len(messages) - len(kept_messages)]

        if not to_summarize:
            log.info("compaction_skipped", reason="nothing_to_summarize")
            return {"skipped": True, "reason": "nothing_to_summarize"}

        # Format messages for summarization
        formatted = self._format_messages_for_summary(to_summarize)

        # Generate summary via LLM
        prompt = self.SUMMARIZE_PROMPT.format(messages=formatted)

        response = await self.llm.complete(
            messages=[{"role": "user", "content": prompt}],
            system="You are a helpful assistant that creates concise conversation summaries.",
        )

        summary_text = response.content

        # Store the summary
        # Note: We need message IDs to properly track ranges
        # For now, just store the summary
        await self.memory.add_summary(summary_text)

        # Delete old messages from DB
        # This requires knowing which messages to delete
        # For now, we'll delete based on count
        deleted = await self._delete_old_messages(len(to_summarize))

        log.info(
            "compaction_complete",
            summarized_messages=len(to_summarize),
            kept_messages=len(kept_messages),
            deleted_messages=deleted,
            summary_tokens=estimate_tokens(summary_text),
        )

        return {
            "skipped": False,
            "summarized": len(to_summarize),
            "kept": len(kept_messages),
            "deleted": deleted,
            "summary_tokens": estimate_tokens(summary_text),
        }

    def _format_messages_for_summary(self, messages: list[dict]) -> str:
        """Format messages into a readable string for summarization."""
        lines = []
        for msg in messages:
            role = msg.get("role", "unknown").upper()
            content = msg.get("content", "")
            lines.append(f"{role}: {content}")
        return "\n\n".join(lines)

    async def _delete_old_messages(self, count: int) -> int:
        """Delete the oldest N messages."""
        if not self.memory._db:
            return 0

        # Get IDs of oldest messages
        cursor = await self.memory._db.execute(
            "SELECT id FROM messages ORDER BY created_at ASC LIMIT ?",
            (count,)
        )
        rows = await cursor.fetchall()
        ids = [row["id"] for row in rows]

        if not ids:
            return 0

        # Delete them
        placeholders = ",".join("?" * len(ids))
        cursor = await self.memory._db.execute(
            f"DELETE FROM messages WHERE id IN ({placeholders})",
            ids
        )
        await self.memory._db.commit()

        return cursor.rowcount


async def ensure_context_headroom(
    memory: SqliteMemoryProvider,
    llm: LLMProvider,
    context_limit: int | None = None,
) -> dict | None:
    """Check context size and compact if needed.

    Call this before processing a request to ensure headroom.

    Returns:
        Compaction stats if compaction was performed, None otherwise
    """
    service = CompactionService(memory, llm, context_limit)

    if await service.needs_compaction():
        return await service.compact()

    return None
