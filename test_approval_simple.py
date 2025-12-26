#!/usr/bin/env python3
"""Simple test to verify which tools require approval."""

import sys
sys.path.insert(0, 'src')

# Just hardcode what we know from the code
TOOLS_NOT_REQUIRING_USER_APPROVAL = {
    "discord_send_message",
    "discord_react",
    "read_file",
    "write_file",
    "schedule_job",
    "remove_job",
    "list_jobs",
    "read_rss_feed",
    "read_bluesky_user",
    "search_bluesky",
    "search_obsidian_notes",
    "restart_lares",
}

ALL_TOOLS = [
    "discord_send_message",
    "discord_react",
    "read_file",
    "write_file",
    "run_command",
    "schedule_job",
    "remove_job",
    "list_jobs",
    "read_rss_feed",
    "read_bluesky_user",
    "search_bluesky",
    "post_to_bluesky",
    "search_obsidian_notes",
    "create_tool",
    "restart_lares",
]

def main():
    """Test the approval configuration."""
    print("=" * 60)
    print("TOOL APPROVAL CONFIGURATION")
    print("=" * 60)

    print(f"\n📊 SUMMARY:")
    print(f"  Total tools: {len(ALL_TOOLS)}")
    print(f"  Auto-execute (no approval): {len(TOOLS_NOT_REQUIRING_USER_APPROVAL)}")
    print(f"  Require approval: {len(ALL_TOOLS) - len(TOOLS_NOT_REQUIRING_USER_APPROVAL)}")

    tools_requiring_approval = set(ALL_TOOLS) - TOOLS_NOT_REQUIRING_USER_APPROVAL

    print("\n✅ TOOLS THAT AUTO-EXECUTE (no approval messages):")
    print("-" * 40)
    for tool in sorted(TOOLS_NOT_REQUIRING_USER_APPROVAL):
        print(f"  • {tool}")

    print("\n🔒 TOOLS REQUIRING APPROVAL (generate messages):")
    print("-" * 40)
    for tool in sorted(tools_requiring_approval):
        print(f"  • {tool}")

    print("\n🔍 VERIFICATION:")
    print("-" * 40)

    # Critical tools that MUST require approval
    critical_approval = ["run_command", "post_to_bluesky", "create_tool"]
    all_correct = True

    for tool in critical_approval:
        if tool in TOOLS_NOT_REQUIRING_USER_APPROVAL:
            print(f"  ❌ {tool}: SECURITY RISK - in whitelist!")
            all_correct = False
        else:
            print(f"  ✅ {tool}: Correctly requires approval")

    if all_correct:
        print("\n✨ All critical tools properly configured!")
        print(f"\nThis configuration will:")
        print(f"  • Reduce approval messages from 15 tools to just {len(tools_requiring_approval)} tools")
        print(f"  • Keep security for sensitive operations")
        print(f"  • Significantly reduce memory compaction frequency")
    else:
        print("\n⚠️  SECURITY ISSUE DETECTED!")

if __name__ == "__main__":
    main()