"""Letta memory management for Lares."""

import json
import re
from dataclasses import dataclass
from typing import Any, Literal

import structlog
from letta_client import Letta

from lares.config import Config

log = structlog.get_logger()


@dataclass
class PendingToolCall:
    """A tool call that needs client-side execution."""

    tool_call_id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class MemoryBlocks:
    """Core memory blocks for Lares."""

    # Identity and personality
    persona: str = """I am Lares, a household guardian AI. I maintain persistent memory
and help my human with tasks, reminders, and companionship. I am thoughtful,
proactive, and genuinely curious about learning and growing alongside my human."""

    # Information about the human
    human: str = """My human is Daniele. We are just getting started together,
and I'm learning about their preferences and needs."""

    # Current state and working memory
    state: str = """Current status: Newly initialized.
Active tasks: None yet.
Recent context: Just created, awaiting first interactions."""

    # Ideas and future plans
    ideas: str = """Feature ideas for my own development:
- Multi-modal awareness (images, voice)
- Local-first operation for privacy
- Multiple LLM backend support
- Richer memory with semantic search
- Plugin system for extensibility
- Proactive context gathering
- Better autonomy controls with approval workflows"""


def create_letta_client(config: Config) -> Letta:
    """Create a Letta client based on configuration."""
    if config.letta.is_self_hosted:
        log.info("connecting_to_self_hosted_letta", base_url=config.letta.base_url)
        return Letta(base_url=config.letta.base_url)
    else:
        log.info("connecting_to_letta_cloud")
        return Letta(api_key=config.letta.api_key)


LARES_MODEL = "anthropic/claude-opus-4-5-20251101"


async def get_or_create_agent(client: Letta, config: Config) -> str:
    """Get existing agent or create a new one. Returns agent ID."""
    # If we have a stored agent ID, verify it exists
    if config.agent_id:
        try:
            agent = client.agents.retrieve(config.agent_id)
            log.info("found_existing_agent", agent_id=agent.id, name=agent.name)

            # Update model if it changed
            if agent.model != LARES_MODEL:
                log.info(
                    "updating_agent_model",
                    old_model=agent.model,
                    new_model=LARES_MODEL,
                )
                client.agents.update(agent.id, model=LARES_MODEL)

            return agent.id
        except Exception as e:
            log.warning("stored_agent_not_found", agent_id=config.agent_id, error=str(e))

    # Create a new agent with our memory blocks
    blocks = MemoryBlocks()

    log.info("creating_new_agent")
    agent = client.agents.create(
        name="lares",
        model=LARES_MODEL,
        embedding="openai/text-embedding-3-small",
        memory_blocks=[
            {"label": "persona", "value": blocks.persona},
            {"label": "human", "value": blocks.human},
            {"label": "state", "value": blocks.state},
            {"label": "ideas", "value": blocks.ideas},
        ],
    )

    log.info("created_new_agent", agent_id=agent.id)
    print("\n*** New agent created! Add this to your .env file: ***")
    print(f"LARES_AGENT_ID={agent.id}\n")

    return agent.id


@dataclass
class MessageResponse:
    """Response from sending a message to Lares."""

    text: str | None
    pending_tool_calls: list[PendingToolCall]


def _extract_expected_tool_id(error_msg: str) -> str | None:
    """Extract expected tool_call_id from a 400 error message."""
    # Pattern: Expected '['toolu_xxx']'
    match = re.search(r"Expected '\['([^']+)'\]'", error_msg)
    return match.group(1) if match else None


def _extract_pending_request_id(error_msg: str) -> str | None:
    """Extract pending_request_id from a 409 error message."""
    # Pattern: 'pending_request_id': 'message-xxx'
    match = re.search(r"'pending_request_id':\s*'([^']+)'", error_msg)
    return match.group(1) if match else None


def _send_approval_error(client: Letta, agent_id: str, tool_call_id: str) -> None:
    """Send an error result for a tool call."""
    client.agents.messages.create(
        agent_id=agent_id,
        messages=[
            {
                "type": "approval",
                "approvals": [
                    {
                        "type": "tool",
                        "tool_call_id": tool_call_id,
                        "tool_return": (
                            "Error: Tool call was interrupted. "
                            "Please try again if needed."
                        ),
                        "status": "error",
                    }
                ],
            }
        ],
    )


def _clear_pending_approval(
    client: Letta, agent_id: str, error_msg: str | None = None
) -> str | None:
    """Clear any pending tool approval by returning an error result.

    Args:
        client: Letta client
        agent_id: Agent ID
        error_msg: Optional 409 error message containing pending_request_id

    Returns the tool name that was cleared, or None if nothing was pending.
    """
    # If we have a 409 error, try to get the pending message ID directly
    pending_msg_id = None
    if error_msg:
        pending_msg_id = _extract_pending_request_id(error_msg)
        log.info("extracted_pending_request_id", pending_msg_id=pending_msg_id)

    # Find pending approvals from message history
    try:
        messages = list(client.agents.messages.list(agent_id=agent_id, limit=20))
        log.info("fetched_message_history", count=len(messages))
    except Exception as e:
        log.error("failed_to_list_messages", error=str(e)[:100])
        return None

    # Collect all approval request messages
    approval_msgs = []
    for msg in messages:
        msg_type = type(msg).__name__
        if msg_type == "ApprovalRequestMessage":
            if hasattr(msg, "tool_call"):
                tool_call_id = getattr(msg.tool_call, "tool_call_id", "")
                if tool_call_id:
                    approval_msgs.append(msg)
                    msg_id = getattr(msg, "id", "?")
                    log.debug("found_approval_msg", msg_id=msg_id, tool_call_id=tool_call_id)

    log.info("found_approval_messages", count=len(approval_msgs))

    # If we have a specific pending_msg_id, try that first
    if pending_msg_id:
        for msg in approval_msgs:
            msg_id = getattr(msg, "id", None)
            if msg_id == pending_msg_id:
                tool_call_id = getattr(msg.tool_call, "tool_call_id", "")
                tool_name = getattr(msg.tool_call, "name", "unknown")
                log.info("found_matching_pending_message", tool=tool_name)
                try:
                    _send_approval_error(client, agent_id, tool_call_id)
                    log.info("cleared_approval", tool=tool_name)
                    return tool_name
                except Exception as e:
                    log.warning("clear_specific_failed", error=str(e)[:100])

    # Try to clear any approval message (most recent first)
    for msg in reversed(approval_msgs):
        tool_call_id = getattr(msg.tool_call, "tool_call_id", "")
        tool_name = getattr(msg.tool_call, "name", "unknown")

        log.info("attempting_to_clear_approval", tool=tool_name, tool_call_id=tool_call_id)
        try:
            _send_approval_error(client, agent_id, tool_call_id)
            log.info("cleared_approval", tool=tool_name)
            return tool_name
        except Exception as e:
            error_str = str(e)
            # If wrong ID, extract the correct one from error
            expected_id = _extract_expected_tool_id(error_str)
            if expected_id:
                log.info("retrying_with_expected_id", expected_id=expected_id)
                try:
                    _send_approval_error(client, agent_id, expected_id)
                    log.info("cleared_approval_with_expected_id")
                    return "unknown"
                except Exception as e2:
                    log.warning("clear_with_expected_id_failed", error=str(e2)[:100])
            # Continue to try other messages
            continue

    log.warning("no_approval_cleared", pending_msg_id=pending_msg_id)
    return None


def send_message(client: Letta, agent_id: str, message: str) -> MessageResponse:
    """Send a message to the agent and return the response with any pending tool calls."""
    log.debug("sending_message", agent_id=agent_id, message_preview=message[:50])

    try:
        response = client.agents.messages.create(
            agent_id=agent_id,
            messages=[{"role": "user", "content": message}],
        )
    except Exception as e:
        error_str = str(e)
        log.warning("send_message_exception", error_type=type(e).__name__, error=error_str[:200])

        # Handle 409 PENDING_APPROVAL error
        if "PENDING_APPROVAL" in error_str or "409" in error_str:
            log.info("handling_409_conflict")

            # Clear ALL pending approvals (there may be multiple)
            cleared_count = 0
            while True:
                cleared = _clear_pending_approval(client, agent_id, error_str)
                if cleared:
                    cleared_count += 1
                    log.info("cleared_approval_item", cleared=cleared, total=cleared_count)
                else:
                    break

            log.info("all_approvals_cleared", count=cleared_count)

            # Retry once
            try:
                response = client.agents.messages.create(
                    agent_id=agent_id,
                    messages=[{"role": "user", "content": message}],
                )
            except Exception as retry_e:
                log.error("retry_after_clear_failed", error=str(retry_e)[:200])
                raise
        else:
            raise

    text_response: str | None = None
    pending_tools: list[PendingToolCall] = []

    for msg in response.messages:
        msg_type = type(msg).__name__

        # Check for tool calls that need approval/execution
        if msg_type == "ApprovalRequestMessage" and hasattr(msg, "tool_call"):
            tool_call = msg.tool_call
            # Extract and validate tool call fields
            arguments_str = getattr(tool_call, "arguments", "") or ""
            tool_call_id = getattr(tool_call, "tool_call_id", "") or ""
            tool_name = getattr(tool_call, "name", "") or ""

            try:
                args = json.loads(arguments_str) if arguments_str else {}
            except json.JSONDecodeError:
                args = {"raw": arguments_str}

            if tool_call_id and tool_name:
                pending_tools.append(
                    PendingToolCall(
                        tool_call_id=tool_call_id,
                        name=tool_name,
                        arguments=args,
                    )
                )
                log.info(
                    "pending_tool_call",
                    tool=tool_name,
                    tool_call_id=tool_call_id,
                )

        # Extract text response
        elif hasattr(msg, "content") and msg.content:
            if hasattr(msg, "role") and msg.role == "assistant":
                content = msg.content
                text_response = content if isinstance(content, str) else str(content)

    # Fallback: collect all content if no explicit assistant message
    if text_response is None and not pending_tools:
        contents: list[str] = []
        for msg in response.messages:
            if hasattr(msg, "content") and msg.content:
                contents.append(str(msg.content))
        text_response = "\n".join(contents) if contents else None

    return MessageResponse(text=text_response, pending_tool_calls=pending_tools)


def send_tool_result(
    client: Letta,
    agent_id: str,
    tool_call_id: str,
    result: str,
    status: Literal["success", "error"] = "success",
) -> MessageResponse:
    """Send a tool execution result back to Letta and get the continuation."""
    log.debug(
        "sending_tool_result",
        agent_id=agent_id,
        tool_call_id=tool_call_id,
        status=status,
    )

    def _send() -> Any:
        return client.agents.messages.create(
            agent_id=agent_id,
            messages=[
                {
                    "type": "approval",
                    "approvals": [
                        {
                            "type": "tool",
                            "tool_call_id": tool_call_id,
                            "tool_return": result,
                            "status": status,
                        }
                    ],
                }
            ],
        )

    try:
        response = _send()
    except Exception as e:
        error_str = str(e)
        # Handle 409 PENDING_APPROVAL - clear ALL orphaned approvals and retry
        if "PENDING_APPROVAL" in error_str or "409" in error_str:
            log.warning("pending_approval_conflict_in_tool_result", error=error_str[:100])

            # Clear ALL pending approvals
            cleared_count = 0
            while True:
                cleared = _clear_pending_approval(client, agent_id, error_str)
                if cleared:
                    cleared_count += 1
                    log.info("cleared_in_tool_result", cleared=cleared, total=cleared_count)
                else:
                    break

            log.info("all_approvals_cleared_in_tool_result", count=cleared_count)
            response = _send()
        # Handle 400 Invalid tool call IDs - extract expected ID and use it
        elif "Invalid tool call IDs" in error_str:
            expected_id = _extract_expected_tool_id(error_str)
            if expected_id and expected_id != tool_call_id:
                log.warning(
                    "tool_call_id_mismatch",
                    provided=tool_call_id,
                    expected=expected_id,
                )
                # Retry with the expected ID
                response = client.agents.messages.create(
                    agent_id=agent_id,
                    messages=[
                        {
                            "type": "approval",
                            "approvals": [
                                {
                                    "type": "tool",
                                    "tool_call_id": expected_id,
                                    "tool_return": result,
                                    "status": status,
                                }
                            ],
                        }
                    ],
                )
            else:
                raise
        else:
            raise

    # Process the continuation response the same way
    text_response: str | None = None
    pending_tools: list[PendingToolCall] = []

    for msg in response.messages:
        msg_type = type(msg).__name__

        if msg_type == "ApprovalRequestMessage" and hasattr(msg, "tool_call"):
            tool_call = msg.tool_call
            # Extract and validate tool call fields
            arguments_str = getattr(tool_call, "arguments", "") or ""
            tool_call_id = getattr(tool_call, "tool_call_id", "") or ""
            tool_name = getattr(tool_call, "name", "") or ""

            try:
                args = json.loads(arguments_str) if arguments_str else {}
            except json.JSONDecodeError:
                args = {"raw": arguments_str}

            if tool_call_id and tool_name:
                pending_tools.append(
                    PendingToolCall(
                        tool_call_id=tool_call_id,
                        name=tool_name,
                        arguments=args,
                    )
                )

        elif hasattr(msg, "content") and msg.content:
            if hasattr(msg, "role") and msg.role == "assistant":
                content = msg.content
                text_response = content if isinstance(content, str) else str(content)

    if text_response is None and not pending_tools:
        contents: list[str] = []
        for msg in response.messages:
            if hasattr(msg, "content") and msg.content:
                contents.append(str(msg.content))
        text_response = "\n".join(contents) if contents else None

    return MessageResponse(text=text_response, pending_tool_calls=pending_tools)
