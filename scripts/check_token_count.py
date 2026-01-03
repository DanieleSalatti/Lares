#!/usr/bin/env python3
"""Check current token count for Lares SQLite memory."""

import asyncio
import os
import sys
from pathlib import Path

# Add src to path so we can import Lares modules
src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))

from lares.compaction import CompactionService, estimate_context_tokens
from lares.providers.anthropic import AnthropicLLMProvider
from lares.providers.sqlite import SqliteMemoryProvider
from lares.utils.token_counter import count_tokens, count_message_tokens


async def main():
    """Check current token count."""
    # Initialize providers
    memory = SqliteMemoryProvider()
    await memory.initialize()
    
    llm = AnthropicLLMProvider()
    await llm.initialize()
    
    # Create compaction service
    compaction = CompactionService(memory, llm)
    
    try:
        # Get context manually and calculate tokens
        context = await memory.get_context()
        summaries = await memory._get_summaries()
        
        base_tokens = count_tokens(context.base_instructions)
        
        block_tokens = 0
        for block in context.blocks:
            block_tokens += count_tokens(block.value)
            block_tokens += count_tokens(block.label)
            block_tokens += count_tokens(block.description)
        
        summary_tokens = sum(count_tokens(s) for s in summaries)
        message_tokens = count_message_tokens(context.messages)
        
        total_tokens = base_tokens + block_tokens + summary_tokens + message_tokens
        
        print("=== Lares Context Token Count ===")
        print(f"Total tokens: {total_tokens:,}")
        print(f"Usage: {round((total_tokens / compaction.context_limit) * 100, 1)}% of {compaction.context_limit:,} limit")
        print()
        print("Breakdown:")
        print(f"  Base instructions: {base_tokens:,} tokens")
        print(f"  Memory blocks:     {block_tokens:,} tokens")
        print(f"  Summaries:         {summary_tokens:,} tokens")
        print(f"  Messages:          {message_tokens:,} tokens ({len(context.messages)} messages)")
        print()
        
        # Check if compaction is needed
        needs_compaction = await compaction.needs_compaction()
        if needs_compaction:
            print("🚨 COMPACTION NEEDED")
            print(f"Context is at {round((total_tokens / compaction.context_limit) * 100, 1)}% - above 70% threshold")
        else:
            print("✅ Context size OK")
            print(f"Context is at {round((total_tokens / compaction.context_limit) * 100, 1)}% - below 70% threshold")
            
    finally:
        await memory.shutdown()
        await llm.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
