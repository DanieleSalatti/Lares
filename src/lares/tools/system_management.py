"""System management tools for Lares self-management."""

import asyncio
import subprocess

import structlog

log = structlog.get_logger()


async def restart_lares() -> str:
    """
    Restart the Lares systemd service.

    This tool allows Lares to restart itself, useful for:
    - Applying code updates after git pull
    - Reloading configuration changes
    - Recovering from suspected issues
    - Periodic fresh starts during autonomous operation

    Requires passwordless sudo access for 'systemctl restart lares.service'.
    See setup-sudoers.sh for configuration.

    Returns:
        Success message. A goodbye message will be sent to Discord before
        the restart happens, making the process graceful.
    """
    log.info("restart_lares_requested")

    # Import here to avoid circular dependency
    from lares.tools.discord import send_message

    try:
        # Send a goodbye message to Discord first
        await send_message("🔄 Restarting now... I'll be back in a moment!", reply=False)
        log.info("restart_goodbye_sent")

        # Give Discord a moment to send the message
        await asyncio.sleep(1)

        # Now execute the restart command
        result = subprocess.run(
            ["sudo", "systemctl", "restart", "lares.service"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )

        if result.returncode == 0:
            log.info("restart_lares_initiated")
            return "Restart initiated successfully."
        else:
            error_msg = result.stderr.strip() or result.stdout.strip()
            log.error("restart_lares_failed", returncode=result.returncode, error=error_msg)
            return f"Failed to restart: {error_msg}"

    except subprocess.TimeoutExpired:
        log.warning("restart_lares_timeout")
        return "Restart command timed out, but may have succeeded. Check systemd status."

    except Exception as e:
        log.error("restart_lares_exception", error=str(e), error_type=type(e).__name__)
        return f"Error restarting: {e}"
