"""Diagnostics support for U-Tec."""
from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_CLIENT_ID, CONF_CLIENT_SECRET
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .coordinator import UhomeDataUpdateCoordinator

# Keys to redact from diagnostic data
REDACT_KEYS = {
    CONF_CLIENT_ID,
    CONF_CLIENT_SECRET,
    "access_token",
    "refresh_token",
    "id_token",
    "token",
    "serial_number",
    "id",
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator: UhomeDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    api = hass.data[DOMAIN][entry.entry_id]["api"]

    # Get device discovery data
    try:
        discovery_data = await api.discover_devices()
    except Exception as err:
        discovery_data = {"error": str(err)}

    # Collect device data
    device_data = {}
    for device_id, device in coordinator.devices.items():
        device_data[device_id] = {
            "name": device.name,
            "handle_type": device.handle_type,
            "category": device.category.value if hasattr(device.category, "value") else device.category,
            "manufacturer": device.manufacturer,
            "model": device.model,
            "hw_version": device.hw_version,
            "supported_capabilities": list(device.supported_capabilities),
            "available": device.available,
            "state_data": device.get_state_data(),
        }

    # Build diagnostics data
    diagnostics_data = {
        "config_entry": async_redact_data(entry.as_dict(), REDACT_KEYS),
        "coordinator_data": {
            "last_update_success": coordinator.last_update_success,
            "device_count": len(coordinator.devices),
        },
        "devices": async_redact_data(device_data, REDACT_KEYS),
        "discovery_data": async_redact_data(discovery_data, REDACT_KEYS),
    }

    return diagnostics_data