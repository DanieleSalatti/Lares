#!/usr/bin/env python3
"""Test DirectLLMHandler standalone.

This script tests the LLM abstraction layer without affecting the live system.
It fetches context from Letta and calls Claude directly.

Usage:
    python scripts/test_direct_llm.py
"""

import os
import sys

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from dotenv import load_dotenv
load_dotenv()

from lares.llm.handler import DirectLLMHandler, HandlerConfig, HandlerResult
from lares.llm.memory_bridge import get_full_context

LETTA_URL = os.getenv("LETTA_BASE_URL", "http://localhost:8283")
AGENT_ID = os.getenv("LETTA_AGENT_ID", "")
ANTHROPIC_KEY = os.getenv("ANTHROPIC_API_KEY", "")


def simple_tool_executor(name: str, args: dict) -> dict:
    """Mock tool executor - just returns what was called."""
    print(f"  [TOOL] {name}({args})")
    return {"status": "mock", "tool": name, "args": args}


def test_context_fetch():
    """Test 1: Can we fetch context from Letta?"""
    print("\n=== Test 1: Fetch Context ===")
    try:
        context = get_full_context(LETTA_URL, AGENT_ID)
        print(f"✓ System prompt: {len(context.system_prompt)} chars")
        print(f"✓ Core memory: {len(context.core_memory)} chars")
        print(f"✓ Messages: {len(context.messages)} items")
        print(f"✓ Tools: {len(context.tools)} available")
        print(f"✓ Tokens: {context.tokens_total} / {context.context_window_max}")
        return True
    except Exception as e:
        print(f"✗ Failed: {e}")
        return False


def test_handler_init():
    """Test 2: Can we initialize the handler?"""
    print("\n=== Test 2: Initialize Handler ===")
    try:
        config = HandlerConfig(
            letta_base_url=LETTA_URL,
            agent_id=AGENT_ID,
            anthropic_api_key=ANTHROPIC_KEY,
            max_tool_iterations=3,  # Limit for testing
        )
        handler = DirectLLMHandler(config=config, tool_executor=simple_tool_executor)
        print(f"✓ Handler initialized with model: {handler.llm.model_name}")
        return handler
    except Exception as e:
        print(f"✗ Failed: {e}")
        return None


def test_simple_message(handler):
    """Test 3: Can we process a simple message?"""
    print("\n=== Test 3: Simple Message (no tools) ===")
    try:
        # Simple message that shouldn't need tools
        result = handler.process_message("What is 2 + 2? Reply with just the number.")
        print(f"✓ Response: {result.response_text[:200]}...")
        print(f"✓ Iterations: {result.total_iterations}")
        print(f"✓ Tool calls: {len(result.tool_calls_made)}")
        print(f"✓ Tokens used: {result.tokens_used}")
        return True
    except Exception as e:
        print(f"✗ Failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    print("=" * 50)
    print("DirectLLMHandler Standalone Test")
    print("=" * 50)
    
    # Check env vars
    if not AGENT_ID:
        print("✗ LETTA_AGENT_ID not set")
        return 1
    if not ANTHROPIC_KEY:
        print("✗ ANTHROPIC_API_KEY not set")
        return 1
    
    print(f"Letta URL: {LETTA_URL}")
    print(f"Agent ID: {AGENT_ID[:30]}...")
    
    # Run tests
    if not test_context_fetch():
        return 1
    
    handler = test_handler_init()
    if not handler:
        return 1
    
    if not test_simple_message(handler):
        return 1
    
    print("\n" + "=" * 50)
    print("All tests passed! ✓")
    print("=" * 50)
    return 0


if __name__ == "__main__":
    sys.exit(main())
