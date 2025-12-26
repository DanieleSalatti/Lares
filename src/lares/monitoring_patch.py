"""
Early monkey-patching for memory monitoring.

This module MUST be imported before any other lares modules to work correctly.
It patches the memory module functions before they can be imported elsewhere.
"""

import os
import sys
from datetime import datetime
from typing import Any, Dict, List
import json
import subprocess
import re


class ContextAnalyzer:
    """Analyze context window usage and compaction patterns."""

    def __init__(self, state_file: str = None):
        self.state_file = state_file or os.path.expanduser("~/.lares/context_analysis.json")
        self.message_history: List[Dict[str, Any]] = []
        self.compaction_events: List[Dict[str, Any]] = []
        self.current_context_size = 0
        self.letta_state_file = os.path.expanduser("~/.lares/letta_context.json")

        # Create directory if needed
        os.makedirs(os.path.dirname(self.state_file), exist_ok=True)

        # Load existing state if available
        self._load_state()

    def _load_state(self):
        """Load state from file if it exists."""
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file, 'r') as f:
                    state = json.load(f)
                    self.message_history = state.get('message_history', [])
                    self.compaction_events = state.get('compaction_events', [])
                    self.current_context_size = state.get('current_context_size', 0)
            except Exception:
                # If load fails, start fresh
                pass

    def _save_state(self):
        """Save current state to file."""
        try:
            state = {
                'message_history': self.message_history[-100:],  # Keep last 100 messages
                'compaction_events': self.compaction_events,
                'current_context_size': self.current_context_size,
                'last_updated': datetime.now().isoformat()
            }

            with open(self.state_file, 'w') as f:
                json.dump(state, f, indent=2)
        except Exception as e:
            print(f"[MONITOR] Failed to save state: {e}")

    def track_message(self, message_type: str, content: str, metadata: Dict = None):
        """Track a message added to context."""
        entry = {
            "timestamp": datetime.now().isoformat(),
            "type": message_type,
            "content_length": len(content) if content else 0,
            "metadata": metadata or {},
            "cumulative_size": self.current_context_size + len(content if content else "")
        }

        self.message_history.append(entry)
        self.current_context_size = entry["cumulative_size"]

        # Save state after each message
        self._save_state()

    def track_compaction(self, summary: str):
        """Track when compaction occurs."""
        # Calculate actual messages compacted
        messages_before = len(self.message_history)

        event = {
            "timestamp": datetime.now().isoformat(),
            "messages_before": messages_before,
            "messages_compacted": max(0, messages_before - 5),  # We keep last 5
            "context_size_before": self.current_context_size,
            "summary_length": len(summary) if summary else 0,
        }

        self.compaction_events.append(event)

        # Reset after compaction - keep last 5 messages for context
        messages_kept = 5
        self.message_history = self.message_history[-messages_kept:]
        self.current_context_size = sum(m["content_length"] for m in self.message_history)

        # Add the compaction summary as a system message
        self.track_message("system_compaction", summary, {"type": "compaction_summary"})

        # Save state after compaction
        self._save_state()

        return event

    def fetch_letta_context(self, agent_id: str):
        """Fetch Letta's actual message history and token count."""
        try:
            import requests

            # First get the agent to see which messages are in context
            agent_response = requests.get(f"http://localhost:8283/v1/agents/{agent_id}")

            if agent_response.status_code != 200:
                print(f"[MONITOR] Failed to get agent info: {agent_response.status_code}")
                return None

            agent_data = agent_response.json()
            context_message_ids = set(agent_data.get("message_ids", []))

            # Get all messages (we need to fetch them to filter)
            response = requests.get(
                f"http://localhost:8283/v1/agents/{agent_id}/messages",
                params={"limit": 500}  # Get more to ensure we have all context messages
            )

            if response.status_code == 200:
                all_messages = response.json()

                # Filter to only messages in the current context
                messages = [msg for msg in all_messages if msg.get("id") in context_message_ids]

                # Count message types
                type_counts = {}
                for msg in messages:
                    msg_type = msg.get("message_type", msg.get("role", "unknown"))
                    type_counts[msg_type] = type_counts.get(msg_type, 0) + 1

                # Get token count from docker logs
                token_count = self._get_letta_token_count()

                letta_data = {
                    "timestamp": datetime.now().isoformat(),
                    "message_count": len(messages),
                    "total_messages_in_db": len(all_messages),
                    "messages_in_context": len(context_message_ids),
                    "message_types": type_counts,
                    "token_estimate": token_count,
                    "messages_sample": messages[:5] if messages else []  # First 5 for inspection
                }

                # Save Letta state
                with open(self.letta_state_file, 'w') as f:
                    json.dump(letta_data, f, indent=2)

                return letta_data
            else:
                print(f"[MONITOR] Failed to fetch Letta messages: {response.status_code}")
                return None

        except Exception as e:
            print(f"[MONITOR] Error fetching Letta context: {e}")
            return None

    def _get_letta_token_count(self):
        """Extract the latest token count from Letta logs."""
        try:
            result = subprocess.run(
                ["docker", "logs", "letta", "--tail", "100"],
                capture_output=True,
                text=True
            )

            # Find the last token estimate
            matches = re.findall(
                r"Context token estimate after .*?: (\d+)",
                result.stderr
            )

            if matches:
                return int(matches[-1])
            return None

        except Exception as e:
            print(f"[MONITOR] Error getting token count: {e}")
            return None


def apply_monitoring_patch():
    """
    Apply the monitoring patch to memory module.
    This must be called before importing any lares modules.
    """
    print("[MONITOR] Applying early patch to memory module", flush=True)

    # Create the analyzer
    analyzer = ContextAnalyzer(state_file=os.path.expanduser("~/.lares/context_analysis.json"))

    # Now import the memory module
    from lares import memory

    # Store original functions
    original_send_message = memory.send_message
    original_send_tool_result = memory.send_tool_result

    print(f"[MONITOR] Original send_message: {original_send_message}", flush=True)
    print(f"[MONITOR] Original send_tool_result: {original_send_tool_result}", flush=True)

    # Create instrumented versions
    def instrumented_send_message(client, agent_id, message, retry_on_compaction=True):
        print(f"[MONITOR] send_message called: {message[:50] if message else 'None'}...", flush=True)
        analyzer.track_message("user_message", message)

        # Call original
        response = original_send_message(client, agent_id, message, retry_on_compaction)

        # Track response (even if empty)
        analyzer.track_message("assistant_response", response.text or "[No text response]")

        # Track compaction if it occurred
        if response.system_alert:
            event = analyzer.track_compaction(response.system_alert)
            print(f"[MONITOR] Compaction detected! Compacted {event['messages_compacted']} messages", flush=True)
            print(f"[MONITOR] Context size: {event['context_size_before']:,} → {analyzer.current_context_size:,} chars", flush=True)

        return response

    def instrumented_send_tool_result(client, agent_id, tool_call_id, result, status="success", retry_on_compaction=True):
        print(f"[MONITOR] send_tool_result called: tool={tool_call_id[:20]}", flush=True)
        analyzer.track_message("tool_result", result, {"tool_id": tool_call_id[:20]})

        # Call original
        response = original_send_tool_result(client, agent_id, tool_call_id, result, status, retry_on_compaction)

        # Track response (even if empty)
        analyzer.track_message("tool_response", response.text or "[No text response]")

        # Track compaction if it occurred
        if response.system_alert:
            event = analyzer.track_compaction(response.system_alert)
            print(f"[MONITOR] Compaction in tool! Compacted {event['messages_compacted']} messages", flush=True)
            print(f"[MONITOR] Context size: {event['context_size_before']:,} → {analyzer.current_context_size:,} chars", flush=True)

        return response

    # Apply patches
    memory.send_message = instrumented_send_message
    memory.send_tool_result = instrumented_send_tool_result
    memory._context_analyzer = analyzer  # Store reference for access

    print("[MONITOR] Memory module patched successfully", flush=True)
    print(f"[MONITOR] Patched send_message: {memory.send_message}", flush=True)
    print(f"[MONITOR] Patched send_tool_result: {memory.send_tool_result}", flush=True)

    return analyzer