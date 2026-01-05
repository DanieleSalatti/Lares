"""System management tools for Lares self-management."""

import asyncio
import os
import subprocess

import aiohttp
import structlog

log = structlog.get_logger()


async def restart_lares() -> str:
    """
    Restart the Lares systemd services (both MCP server and main bot).

    This tool allows Lares to restart itself, useful for:
    - Applying code updates after git pull
    - Reloading configuration changes
    - Recovering from suspected issues
    - Periodic fresh starts during autonomous operation

    Requires passwordless sudo access for:
    - '/usr/bin/systemctl restart lares-mcp.service'
    - '/usr/bin/systemctl restart lares.service'
    See setup-sudoers.sh for configuration.

    Returns:
        Success message confirming restart was initiated.
    """
    log.info("restart_lares_requested")

    mcp_url = os.getenv("LARES_MCP_URL", "http://localhost:8765")

    try:
        # Send a goodbye message to Discord via MCP HTTP endpoint
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{mcp_url}/discord/send",
                json={"content": "🔄 Restarting now... I'll be back in a moment!"}
            ) as resp:
                if resp.status == 200:
                    log.info("restart_goodbye_sent")
                else:
                    log.warning("restart_goodbye_failed", status=resp.status)

        # Give Discord a moment to send the message
        await asyncio.sleep(1)

        # Fire-and-forget: spawn restart as detached process so we can return
        # before systemd kills us. start_new_session=True ensures the process
        # survives our death.
        #
        # We restart MCP first (quick), then Lares main service.
        # Using shell=True to chain commands properly.
        # NOTE: Must use full path /usr/bin/systemctl to match sudoers config!
        restart_cmd = (
            "sudo /usr/bin/systemctl restart lares-mcp.service; "
            "sudo /usr/bin/systemctl restart lares.service"
        )
        subprocess.Popen(
            restart_cmd,
            shell=True,
            start_new_session=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        log.info("restart_lares_initiated", services=["lares-mcp", "lares"])
        return "Restart initiated! Goodbye... 👋"

    except Exception as e:
        log.error(
            "restart_lares_exception", error=str(e), error_type=type(e).__name__
        )
        return f"Error restarting: {e}"


async def restart_mcp() -> str:
    """
    Restart only the Lares MCP server (not the main bot).

    Use this when:
    - New MCP tools have been added
    - MCP server configuration changed
    - MCP server is having issues

    This is faster than a full restart since Lares main bot stays running.

    Requires passwordless sudo access for '/usr/bin/systemctl restart lares-mcp.service'.
    See setup-sudoers.sh for configuration.

    Returns:
        Success message confirming MCP restart was initiated.
    """
    log.info("restart_mcp_requested")

    mcp_url = os.getenv("LARES_MCP_URL", "http://localhost:8765")

    try:
        # NOTE: Must use full path /usr/bin/systemctl to match sudoers config!
        result = subprocess.run(
            ["sudo", "/usr/bin/systemctl", "restart", "lares-mcp.service"],
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode == 0:
            log.info("restart_mcp_completed")
            # Send success message via MCP HTTP endpoint
            async with aiohttp.ClientSession() as session:
                await session.post(
                    f"{mcp_url}/discord/send",
                    json={"content": "🔄 MCP server restarted successfully!"}
                )
            return "MCP server restarted successfully! ✅"
        else:
            error_msg = result.stderr or "Unknown error"
            log.error("restart_mcp_failed", error=error_msg)
            return f"Error restarting MCP server: {error_msg}"

    except subprocess.TimeoutExpired:
        log.error("restart_mcp_timeout")
        return "Error: MCP restart timed out after 30 seconds"
    except Exception as e:
        log.error("restart_mcp_exception", error=str(e), error_type=type(e).__name__)
        return f"Error restarting MCP: {e}"
