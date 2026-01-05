"""Home Assistant integration tools for Lares."""

import os
from pathlib import Path

import aiohttp
import structlog

from .base import ToolError, ToolResult

log = structlog.get_logger()


def _get_ha_config() -> tuple[str, str]:
    """
    Get Home Assistant URL and token from environment.

    First checks environment variables, then falls back to reading .env file.

    Returns:
        Tuple of (url, token)

    Raises:
        ToolError: If configuration is missing
    """
    # Try environment variables first
    url = os.getenv("HASS_URL") or os.getenv("HOME_ASSISTANT_URL")
    token = os.getenv("HASS_TOKEN") or os.getenv("HOME_ASSISTANT_TOKEN")

    # Fall back to reading .env file if not in environment
    if not url or not token:
        env_path = Path("/home/daniele/workspace/lares/.env")
        if env_path.exists():
            env_vars = {}
            for line in env_path.read_text().splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, value = line.partition("=")
                    # Strip quotes from value
                    value = value.strip().strip('"').strip("'")
                    env_vars[key.strip()] = value

            url = url or env_vars.get("HASS_URL") or env_vars.get("HOME_ASSISTANT_URL")
            token = token or env_vars.get("HASS_TOKEN") or env_vars.get("HOME_ASSISTANT_TOKEN")

    if not url:
        raise ToolError("Home Assistant URL not configured (HASS_URL or HOME_ASSISTANT_URL)")
    if not token:
        raise ToolError("Home Assistant token not configured (HASS_TOKEN or HOME_ASSISTANT_TOKEN)")

    return url.rstrip("/"), token


async def ha_turn_on(entity_id: str) -> ToolResult:
    """
    Turn on a Home Assistant entity.

    Args:
        entity_id: The entity ID to turn on (e.g., "light.living_room", "switch.fan")

    Returns:
        ToolResult with success/failure status
    """
    log.info("ha_turn_on", entity_id=entity_id)

    try:
        url, token = _get_ha_config()
    except ToolError as e:
        return ToolResult(success=False, message=str(e))

    # Determine service based on entity type
    domain = entity_id.split(".")[0] if "." in entity_id else "homeassistant"
    service = "turn_on"

    api_url = f"{url}/api/services/{domain}/{service}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                api_url,
                headers=headers,
                json={"entity_id": entity_id}
            ) as resp:
                if resp.status == 200:
                    log.info("ha_turn_on_success", entity_id=entity_id)
                    return ToolResult(
                        success=True,
                        message=f"✅ Turned on {entity_id}",
                        data={"entity_id": entity_id, "state": "on"}
                    )
                else:
                    error_text = await resp.text()
                    log.error("ha_turn_on_failed", entity_id=entity_id, status=resp.status)
                    return ToolResult(
                        success=False,
                        message=f"Failed to turn on {entity_id}: HTTP {resp.status} - {error_text}"
                    )
    except aiohttp.ClientError as e:
        log.error("ha_turn_on_error", entity_id=entity_id, error=str(e))
        return ToolResult(success=False, message=f"Connection error: {e}")


async def ha_turn_off(entity_id: str) -> ToolResult:
    """
    Turn off a Home Assistant entity.

    Args:
        entity_id: The entity ID to turn off (e.g., "light.living_room", "switch.fan")

    Returns:
        ToolResult with success/failure status
    """
    log.info("ha_turn_off", entity_id=entity_id)

    try:
        url, token = _get_ha_config()
    except ToolError as e:
        return ToolResult(success=False, message=str(e))

    # Determine service based on entity type
    domain = entity_id.split(".")[0] if "." in entity_id else "homeassistant"
    service = "turn_off"

    api_url = f"{url}/api/services/{domain}/{service}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                api_url,
                headers=headers,
                json={"entity_id": entity_id}
            ) as resp:
                if resp.status == 200:
                    log.info("ha_turn_off_success", entity_id=entity_id)
                    return ToolResult(
                        success=True,
                        message=f"✅ Turned off {entity_id}",
                        data={"entity_id": entity_id, "state": "off"}
                    )
                else:
                    error_text = await resp.text()
                    log.error("ha_turn_off_failed", entity_id=entity_id, status=resp.status)
                    return ToolResult(
                        success=False,
                        message=f"Failed to turn off {entity_id}: HTTP {resp.status} - {error_text}"
                    )
    except aiohttp.ClientError as e:
        log.error("ha_turn_off_error", entity_id=entity_id, error=str(e))
        return ToolResult(success=False, message=f"Connection error: {e}")


async def ha_get_state(entity_id: str) -> ToolResult:
    """
    Get the current state of a Home Assistant entity.

    Args:
        entity_id: The entity ID to query (e.g., "light.living_room")

    Returns:
        ToolResult with entity state information
    """
    log.info("ha_get_state", entity_id=entity_id)

    try:
        url, token = _get_ha_config()
    except ToolError as e:
        return ToolResult(success=False, message=str(e))

    api_url = f"{url}/api/states/{entity_id}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(api_url, headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    state = data.get("state", "unknown")
                    friendly_name = data.get("attributes", {}).get("friendly_name", entity_id)
                    log.info("ha_get_state_success", entity_id=entity_id, state=state)
                    return ToolResult(
                        success=True,
                        message=f"📊 {friendly_name}: {state}",
                        data=data
                    )
                elif resp.status == 404:
                    return ToolResult(
                        success=False,
                        message=f"Entity not found: {entity_id}"
                    )
                else:
                    error_text = await resp.text()
                    log.error("ha_get_state_failed", entity_id=entity_id, status=resp.status)
                    return ToolResult(
                        success=False,
                        message=f"Failed to get state: HTTP {resp.status} - {error_text}"
                    )
    except aiohttp.ClientError as e:
        log.error("ha_get_state_error", entity_id=entity_id, error=str(e))
        return ToolResult(success=False, message=f"Connection error: {e}")


async def ha_list_entities(domain: str = None) -> ToolResult:
    """
    List available Home Assistant entities, optionally filtered by domain.

    Args:
        domain: Optional domain filter (e.g., "light", "switch", "sensor")

    Returns:
        ToolResult with list of entities
    """
    log.info("ha_list_entities", domain=domain)

    try:
        url, token = _get_ha_config()
    except ToolError as e:
        return ToolResult(success=False, message=str(e))

    api_url = f"{url}/api/states"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(api_url, headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    entities = []
                    for entity in data:
                        entity_id = entity.get("entity_id", "")
                        if domain is None or entity_id.startswith(f"{domain}."):
                            friendly_name = entity.get("attributes", {}).get(
                                "friendly_name", entity_id
                            )
                            state = entity.get("state", "unknown")
                            entities.append({
                                "entity_id": entity_id,
                                "friendly_name": friendly_name,
                                "state": state
                            })

                    # Sort by entity_id for consistent output
                    entities.sort(key=lambda x: x["entity_id"])

                    # Format output
                    domain_str = f" ({domain})" if domain else ""
                    lines = [f"🏠 Home Assistant Entities{domain_str}:"]
                    for e in entities[:50]:  # Limit to 50 to avoid huge output
                        lines.append(f"  • {e['friendly_name']}: {e['state']} [{e['entity_id']}]")

                    if len(entities) > 50:
                        lines.append(f"  ... and {len(entities) - 50} more")

                    log.info("ha_list_entities_success", count=len(entities))
                    return ToolResult(
                        success=True,
                        message="\n".join(lines),
                        data={"entities": entities, "total": len(entities)}
                    )
                else:
                    error_text = await resp.text()
                    log.error("ha_list_entities_failed", status=resp.status)
                    return ToolResult(
                        success=False,
                        message=f"Failed to list entities: HTTP {resp.status} - {error_text}"
                    )
    except aiohttp.ClientError as e:
        log.error("ha_list_entities_error", error=str(e))
        return ToolResult(success=False, message=f"Connection error: {e}")


async def ha_set_light_brightness(entity_id: str, brightness: int) -> ToolResult:
    """
    Set the brightness of a light entity.

    Args:
        entity_id: The light entity ID (e.g., "light.living_room")
        brightness: Brightness level 0-255 (0=off, 255=full brightness)

    Returns:
        ToolResult with success/failure status
    """
    log.info("ha_set_light_brightness", entity_id=entity_id, brightness=brightness)

    if not entity_id.startswith("light."):
        return ToolResult(
            success=False,
            message=f"Entity must be a light (got {entity_id})"
        )

    if not 0 <= brightness <= 255:
        return ToolResult(
            success=False,
            message=f"Brightness must be 0-255 (got {brightness})"
        )

    try:
        url, token = _get_ha_config()
    except ToolError as e:
        return ToolResult(success=False, message=str(e))

    api_url = f"{url}/api/services/light/turn_on"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                api_url,
                headers=headers,
                json={"entity_id": entity_id, "brightness": brightness}
            ) as resp:
                if resp.status == 200:
                    pct = round(brightness / 255 * 100)
                    log.info("ha_set_brightness_success", entity_id=entity_id, brt=brightness)
                    return ToolResult(
                        success=True,
                        message=f"💡 Set {entity_id} brightness to {pct}%",
                        data={"entity_id": entity_id, "brightness": brightness}
                    )
                else:
                    error_text = await resp.text()
                    log.error("ha_set_brightness_failed", entity_id=entity_id, status=resp.status)
                    return ToolResult(
                        success=False,
                        message=f"Failed to set brightness: HTTP {resp.status} - {error_text}"
                    )
    except aiohttp.ClientError as e:
        log.error("ha_set_brightness_error", entity_id=entity_id, error=str(e))
        return ToolResult(success=False, message=f"Connection error: {e}")
