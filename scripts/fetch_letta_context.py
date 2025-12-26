#!/usr/bin/env python3
"""
Fetch Letta's actual context and save it for analysis.
This shows what Letta really sees vs what our monitoring tracks.
"""

import sys
import os
import json

sys.path.insert(0, 'src')

# Get agent ID from env or command line
agent_id = sys.argv[1] if len(sys.argv) > 1 else os.getenv("LARES_AGENT_ID", "agent-9715d6d6-84ed-4bff-b767-32b90ca4f5a6")

from lares.monitoring_patch import ContextAnalyzer

print(f"Fetching Letta context for agent: {agent_id}")
print("-" * 50)

# Create analyzer and fetch
analyzer = ContextAnalyzer()
letta_data = analyzer.fetch_letta_context(agent_id)

if letta_data:
    print(f"✅ Fetched {letta_data['message_count']} messages")
    print(f"   Token estimate: {letta_data.get('token_estimate', 'unknown')}")

    if letta_data.get('message_types'):
        print("\nMessage types in Letta:")
        for msg_type, count in sorted(letta_data['message_types'].items()):
            print(f"  - {msg_type}: {count}")

    print(f"\n💾 Saved to: ~/.lares/letta_context.json")
    print("   Run ./scripts/memory-report to see the comparison")
else:
    print("❌ Failed to fetch Letta context")
    print("   Check that Letta is running and the agent ID is correct")