#!/usr/bin/env python3
"""Test script to verify approval message reduction."""

import sys
sys.path.insert(0, 'src')

from lares.tool_registry import TOOLS_NOT_REQUIRING_USER_APPROVAL, get_all_tools

def main():
    """Test the approval configuration."""
    print("=" * 60)
    print("TOOL APPROVAL CONFIGURATION TEST")
    print("=" * 60)

    # Get all tools
    tools = get_all_tools()

    print(f"\nTotal tools available: {len(tools)}")
    print(f"Tools in whitelist (auto-execute): {len(TOOLS_NOT_REQUIRING_USER_APPROVAL)}")
    print(f"Tools requiring approval: {len(tools) - len(TOOLS_NOT_REQUIRING_USER_APPROVAL)}")

    print("\n" + "=" * 60)
    print("TOOLS THAT AUTO-EXECUTE (no approval messages):")
    print("=" * 60)
    for tool_name in sorted(TOOLS_NOT_REQUIRING_USER_APPROVAL):
        if tool_name in tools:
            print(f"  ✓ {tool_name}")
        else:
            print(f"  ✗ {tool_name} (NOT FOUND IN REGISTRY!)")

    print("\n" + "=" * 60)
    print("TOOLS REQUIRING APPROVAL (generate approval messages):")
    print("=" * 60)
    tools_requiring_approval = set(tools.keys()) - TOOLS_NOT_REQUIRING_USER_APPROVAL
    for tool_name in sorted(tools_requiring_approval):
        print(f"  🔒 {tool_name}")

    # Check if the critical tools are correctly configured
    print("\n" + "=" * 60)
    print("CRITICAL TOOL VERIFICATION:")
    print("=" * 60)

    critical_approval_required = ["run_command", "post_to_bluesky", "create_tool"]
    for tool in critical_approval_required:
        if tool in tools:
            if tool in TOOLS_NOT_REQUIRING_USER_APPROVAL:
                print(f"  ❌ {tool}: INCORRECTLY IN WHITELIST (SECURITY RISK!)")
            else:
                print(f"  ✅ {tool}: Correctly requires approval")
        else:
            print(f"  ⚠️  {tool}: Not found in registry")

    # Check that common tools don't require approval
    common_tools = ["discord_send_message", "read_file", "write_file", "search_obsidian_notes"]
    print("\nCommon tools (should auto-execute):")
    for tool in common_tools:
        if tool in tools:
            if tool in TOOLS_NOT_REQUIRING_USER_APPROVAL:
                print(f"  ✅ {tool}: Auto-executes (no approval messages)")
            else:
                print(f"  ❌ {tool}: Requires approval (WILL CREATE MESSAGES)")
        else:
            print(f"  ⚠️  {tool}: Not found in registry")

if __name__ == "__main__":
    main()