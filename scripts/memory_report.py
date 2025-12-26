#!/usr/bin/env python3
"""
Get memory compaction report from Lares context analyzer.

This script shows:
- Current context size
- Compaction events and triggers
- Average stats
- Recent compaction history

Usage:
    # Option 1: Use the wrapper script (recommended)
    ./scripts/memory-report

    # Option 2: Use venv Python directly
    .venv/bin/python scripts/memory_report.py

    # Option 3: Activate venv first
    source .venv/bin/activate
    python scripts/memory_report.py

Note: Requires LARES_CONTEXT_MONITORING=true in .env and Lares must be running.
"""

import sys
import os
import json
from datetime import datetime


def get_report():
    """Get the memory report from the context analyzer."""
    # Load state from file
    state_file = os.path.expanduser("~/.lares/context_analysis.json")
    letta_file = os.path.expanduser("~/.lares/letta_context.json")

    if not os.path.exists(state_file):
        print("❌ No monitoring data found. Make sure:")
        print("   1. LARES_CONTEXT_MONITORING=true in .env")
        print("   2. Lares has been restarted with monitoring enabled")
        print("   3. Some messages have been processed")
        print(f"\nExpected file: {state_file}")
        return False

    try:
        with open(state_file, 'r') as f:
            state = json.load(f)

        # Create a simple analyzer-like object to work with existing code
        class AnalyzerState:
            def __init__(self, data):
                self.message_history = data.get('message_history', [])
                self.compaction_events = data.get('compaction_events', [])
                self.current_context_size = data.get('current_context_size', 0)
                self.last_updated = data.get('last_updated', 'unknown')

            def generate_report(self):
                """Generate analysis report."""
                if not self.compaction_events:
                    return "No compaction events recorded yet."

                report = ["Context Window Analysis Report", "=" * 40, ""]
                report.append(f"Total compaction events: {len(self.compaction_events)}")
                report.append(f"Current context size: {self.current_context_size:,} chars")
                report.append(f"Messages in history: {len(self.message_history)}")
                report.append("")

                # Compaction patterns
                if any("trigger_pattern" in event for event in self.compaction_events):
                    report.append("Compaction Triggers:")
                    triggers = {}
                    for event in self.compaction_events:
                        if "trigger_pattern" in event:
                            trigger = event["trigger_pattern"]["trigger"]
                            triggers[trigger] = triggers.get(trigger, 0) + 1

                    for trigger, count in sorted(triggers.items(), key=lambda x: x[1], reverse=True):
                        report.append(f"  - {trigger}: {count} times")
                else:
                    # Simplified view without trigger patterns
                    report.append("Recent Compactions:")
                    for event in self.compaction_events[-5:]:  # Last 5
                        report.append(f"  - {event['timestamp']}: {event['messages_compacted']} messages compacted")

                return "\n".join(report)

        analyzer = AnalyzerState(state)

        # Print header
        print("=" * 60)
        print("LARES MEMORY COMPACTION REPORT")
        print(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 60)

        # Show OUR tracking
        print("\n📊 OUR TRACKING (what we intercept):")
        print("-" * 40)
        print(f"Messages tracked: {len(analyzer.message_history)}")
        print(f"Context size: {analyzer.current_context_size:,} chars")

        # Count our message types
        our_types = {}
        for msg in analyzer.message_history:
            t = msg.get('type', 'unknown')
            our_types[t] = our_types.get(t, 0) + 1

        print("Message types:")
        for msg_type, count in sorted(our_types.items()):
            print(f"  - {msg_type}: {count}")

        # Show Letta's view if available
        if os.path.exists(letta_file):
            try:
                with open(letta_file, 'r') as f:
                    letta_data = json.load(f)

                print("\n🔍 LETTA'S VIEW (actual context):")
                print("-" * 40)
                print(f"Messages in history: {letta_data.get('message_count', 'unknown')}")
                print(f"Estimated tokens: {letta_data.get('token_estimate', 'unknown'):,}" if letta_data.get('token_estimate') else "Estimated tokens: unknown")

                if letta_data.get('message_types'):
                    print("Message types:")
                    for msg_type, count in sorted(letta_data['message_types'].items()):
                        print(f"  - {msg_type}: {count}")

                # Show discrepancy analysis
                if letta_data.get('message_count'):
                    our_count = len(analyzer.message_history)
                    letta_count = letta_data['message_count']
                    hidden = letta_count - our_count

                    print("\n⚠️  DISCREPANCY ANALYSIS:")
                    print("-" * 40)
                    print(f"Hidden messages: {hidden} ({hidden*100//letta_count}% of total)")

                    if letta_data.get('token_estimate') and analyzer.current_context_size > 0:
                        char_per_token = analyzer.current_context_size / letta_data['token_estimate']
                        print(f"Chars per token (our view): {char_per_token:.2f}")

                    print(f"Last Letta update: {letta_data.get('timestamp', 'unknown')}")

            except Exception as e:
                print(f"\n⚠️  Could not load Letta data: {e}")
        else:
            print("\n💡 TIP: Update Letta context with: python -c \"from lares.memory import _context_analyzer; _context_analyzer.fetch_letta_context('agent-id')\"")

        print("\n" + "=" * 60)
        print("COMPACTION HISTORY")
        print("=" * 60)

        # Print the report
        print(analyzer.generate_report())

        # Print additional live stats
        print("\n" + "=" * 60)
        print("CURRENT STATUS")
        print("=" * 60)
        print(f"Our context size: {analyzer.current_context_size:,} chars")
        print(f"Messages tracked: {len(analyzer.message_history)}")
        print(f"Total compactions: {len(analyzer.compaction_events)}")

        # Show last compaction if any
        if analyzer.compaction_events:
            last = analyzer.compaction_events[-1]
            print(f"\nLast compaction:")
            print(f"  Time: {last['timestamp']}")
            if 'trigger_pattern' in last:
                print(f"  Trigger: {last['trigger_pattern']['trigger']}")
            else:
                print(f"  Messages compacted: {last.get('messages_compacted', 'unknown')}")
            print(f"  Size before: {last['context_size_before']:,} chars")
            print(f"  Messages compacted: {last['messages_compacted']}")

        return True

    except ImportError as e:
        if "_context_analyzer" in str(e):
            print("❌ Context analyzer not available.")
            print("   Possible reasons:")
            print("   1. LARES_CONTEXT_MONITORING is not set to true")
            print("   2. Lares is not running")
            print("   3. Lares was started without monitoring enabled")
            print("\nTo enable monitoring:")
            print("   1. Set LARES_CONTEXT_MONITORING=true in .env")
            print("   2. Restart Lares")
        else:
            print(f"❌ Import error: {e}")
            print("   Make sure you're in the Lares directory and virtual env is active")
        return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False


def export_json(filename=None):
    """Export the compaction events to JSON for analysis."""
    state_file = os.path.expanduser("~/.lares/context_analysis.json")

    if not os.path.exists(state_file):
        print("❌ No monitoring data found")
        return False

    try:
        with open(state_file, 'r') as f:
            state = json.load(f)

        if not filename:
            filename = f"compaction_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

        # Just copy the state with metadata
        export_data = {
            "generated": datetime.now().isoformat(),
            "current_context_size": state.get('current_context_size', 0),
            "message_count": len(state.get('message_history', [])),
            "compaction_events": state.get('compaction_events', []),
            "recent_messages": state.get('message_history', [])[-10:]
        }

        with open(filename, 'w') as f:
            json.dump(export_data, f, indent=2)

        print(f"✅ Exported to {filename}")
        return True

    except Exception as e:
        print(f"❌ Export failed: {e}")
        return False


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description='Get Lares memory compaction report')
    parser.add_argument('--export', '-e', help='Export to JSON file', nargs='?', const=True)
    parser.add_argument('--brief', '-b', action='store_true', help='Show brief summary only')

    args = parser.parse_args()

    if args.export:
        # If --export is given a filename, use it; otherwise generate one
        filename = args.export if isinstance(args.export, str) else None
        export_json(filename)
    elif args.brief:
        # Brief mode - just key stats
        state_file = os.path.expanduser("~/.lares/context_analysis.json")
        if os.path.exists(state_file):
            try:
                with open(state_file, 'r') as f:
                    state = json.load(f)

                print(f"Context: {state.get('current_context_size', 0):,} chars | ", end="")
                print(f"Messages: {len(state.get('message_history', []))} | ", end="")
                print(f"Compactions: {len(state.get('compaction_events', []))}")

                events = state.get('compaction_events', [])
                if events:
                    if any('trigger_pattern' in e for e in events):
                        triggers = {}
                        for event in events:
                            if 'trigger_pattern' in event:
                                t = event['trigger_pattern']['trigger']
                                triggers[t] = triggers.get(t, 0) + 1
                        print(f"Triggers: {triggers}")
                    else:
                        print(f"Last compaction: {events[-1]['timestamp']}, {events[-1].get('messages_compacted', '?')} msgs")
            except:
                print("Error reading monitoring data")
        else:
            print("Monitoring not active")
    else:
        # Full report
        get_report()


if __name__ == "__main__":
    main()