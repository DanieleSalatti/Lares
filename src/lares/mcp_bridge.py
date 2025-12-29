"""
MCP Approval Bridge - Connects MCP approval queue to Discord.

This component:
1. Polls the MCP server for pending approvals
2. Sends approval requests to Discord
3. Handles reactions to approve/deny/remember
4. Calls back to MCP with the decision

Can be integrated into main Lares process or run standalone.
"""

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass

# Configuration
MCP_SERVER_URL = os.getenv("MCP_SERVER_URL", "http://127.0.0.1:8765")
POLL_INTERVAL = int(os.getenv("MCP_POLL_INTERVAL", "5"))


@dataclass
class PendingApproval:
    """Tracks a pending approval and its Discord message."""

    approval_id: str
    tool: str
    args: dict
    message_id: int | None = None
    created_at: str = ""


class MCPApprovalBridge:
    """Bridge between MCP approval queue and Discord."""

    def __init__(self):
        self.pending: dict[str, PendingApproval] = {}
        self.message_to_approval: dict[int, str] = {}
        self._send_message = None  # Callback to send Discord messages
        self._edit_message = None  # Callback to edit Discord messages

    def set_callbacks(self, send_message, edit_message):
        """Set the Discord message callbacks."""
        self._send_message = send_message
        self._edit_message = edit_message

    def _mcp_request(self, path: str, method: str = "GET") -> dict | None:
        """Make a request to the MCP server."""
        try:
            url = f"{MCP_SERVER_URL}{path}"
            req = urllib.request.Request(url, method=method)
            with urllib.request.urlopen(req, timeout=10) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.URLError:
            # Server not running - not an error during normal operation
            return None
        except Exception as e:
            print(f"MCP request error: {e}")
            return None

    async def poll_approvals(self) -> list[PendingApproval]:
        """Poll MCP for new pending approvals. Returns list of new items."""
        data = self._mcp_request("/approvals/pending")
        if not data:
            return []

        new_approvals = []
        for item in data.get("pending", []):
            approval_id = item["id"]

            if approval_id in self.pending:
                continue

            args = item["args"]
            if isinstance(args, str):
                args = json.loads(args)

            pending = PendingApproval(
                approval_id=approval_id,
                tool=item["tool"],
                args=args,
                created_at=item.get("created_at", ""),
            )
            self.pending[approval_id] = pending
            new_approvals.append(pending)

        return new_approvals

    def format_approval_message(self, pending: PendingApproval) -> str:
        """Format an approval request for Discord."""
        args_str = json.dumps(pending.args, indent=2)
        if len(args_str) > 500:
            args_str = args_str[:500] + "\n..."

        # Add 🔓 option for shell commands
        if pending.tool in ("run_shell_command", "run_command"):
            react_help = "React ✅ approve once, 🔓 approve & remember, ❌ deny"
        else:
            react_help = "React ✅ to approve, ❌ to deny"

        return (
            f"🔒 **Approval Required** [`{pending.approval_id}`]\n"
            f"**Tool:** `{pending.tool}`\n"
            f"```json\n{args_str}\n```\n"
            f"{react_help}"
        )

    def track_message(self, approval_id: str, message_id: int):
        """Track which Discord message corresponds to which approval."""
        if approval_id in self.pending:
            self.pending[approval_id].message_id = message_id
            self.message_to_approval[message_id] = approval_id

    def handle_reaction(self, message_id: int, emoji: str) -> tuple[str, str, str, str] | None:
        """
        Handle a reaction. Returns (approval_id, status, tool, result_text) or None.

        Status can be: "approved", "denied", "approved_and_remembered"
        """
        approval_id = self.message_to_approval.get(message_id)
        if not approval_id:
            return None

        pending = self.pending.get(approval_id)
        if not pending:
            return None

        if emoji == "✅":
            result = self._mcp_request(f"/approvals/{approval_id}/approve", "POST")
            status = "approved"
        elif emoji == "🔓":
            result = self._mcp_request(f"/approvals/{approval_id}/remember", "POST")
            if result and result.get("status") == "approved_and_remembered":
                status = "approved_and_remembered"
            else:
                # Fallback if remember fails (e.g., non-shell command)
                result = self._mcp_request(f"/approvals/{approval_id}/approve", "POST")
                status = "approved"
        elif emoji == "❌":
            result = self._mcp_request(f"/approvals/{approval_id}/deny", "POST")
            status = "denied"
        else:
            return None

        # Clean up tracking
        del self.pending[approval_id]
        if message_id in self.message_to_approval:
            del self.message_to_approval[message_id]

        result_text = ""
        pattern = ""
        if result:
            if "result" in result:
                result_text = result["result"]
                if len(result_text) > 500:
                    result_text = result_text[:500] + "\n..."
            if "pattern" in result:
                pattern = result["pattern"]
                status = f"approved_and_remembered (pattern: `{pattern}`)"

        return (approval_id, status, pending.tool, result_text)

    def health_check(self) -> dict | None:
        """Check MCP server health."""
        return self._mcp_request("/health")


# Singleton instance
_bridge: MCPApprovalBridge | None = None


def get_bridge() -> MCPApprovalBridge:
    """Get or create the bridge singleton."""
    global _bridge
    if _bridge is None:
        _bridge = MCPApprovalBridge()
    return _bridge
