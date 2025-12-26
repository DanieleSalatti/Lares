#!/usr/bin/env python3
"""Test Letta connection."""

import sys
sys.path.insert(0, 'src')

import os
from letta_client import Letta

def test_connection():
    """Test if we can connect to Letta."""
    try:
        print("Testing Letta connection...")

        # Get Letta URL from environment
        letta_url = os.getenv("LETTA_API_URL", "http://localhost:8283")
        print(f"Connecting to: {letta_url}")

        # Create client
        client = Letta(
            base_url=letta_url,
        )

        # List agents
        agents = list(client.agents.list())  # Convert to list
        print(f"✅ Connected successfully!")
        print(f"Found {len(agents)} agent(s)")

        for agent in agents:
            print(f"  - {agent.name} (ID: {agent.id})")

        # Get the lares agent
        lares_agent = next((a for a in agents if a.name == "lares"), None)
        if lares_agent:
            print(f"\n✅ Lares agent found: {lares_agent.id}")
            print(f"  State: Ready to start")
        else:
            print("\n❌ Lares agent not found!")

        return True

    except Exception as e:
        print(f"\n❌ Connection failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_connection()
    sys.exit(0 if success else 1)