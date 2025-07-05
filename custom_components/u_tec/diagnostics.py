"""Diagnostics support for Uhome."""

from __future__ import annotations

import json
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
    coordinator: UhomeDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id][
        "coordinator"
    ]
    api = hass.data[DOMAIN][entry.entry_id]["api"]

    # Get device discovery data
    try:
        discovery_data = await api.discover_devices()
    except ConnectionError as err:
        discovery_data = {"error": f"Connection error: {err!s}"}
    except TimeoutError as err:
        discovery_data = {"error": f"Timeout error: {err!s}"}
    except ValueError as err:
        discovery_data = {"error": f"Value error: {err!s}"}

    # Collect device data
    device_data = {}
    query_data = {}
    for device_id, device in coordinator.devices.items():
        device_properties = {}
        for prop_name in dir(device):
            # Skip private properties and methods
            if prop_name.startswith("_") or callable(getattr(device, prop_name)):
                continue

            try:
                value = getattr(device, prop_name)
                # Convert enum values to strings
                if hasattr(value, "value"):
                    value = value.value
                # Skip properties that can't be serialized
                try:
                    json.dumps({"test": value})
                    device_properties[prop_name] = value
                except (TypeError, OverflowError):
                    device_properties[prop_name] = str(value)

            except AttributeError as err:
                device_properties[prop_name] = f"Attribute error: {err!s}"
            except ValueError as err:
                device_properties[prop_name] = f"Value error: {err!s}"

        device_data[device_id] = {
            "name": device.name,
            "handle_type": device.handle_type,
            "category": device.category.value
            if hasattr(device.category, "value")
            else device.category,
            "manufacturer": device.manufacturer,
            "model": device.model,
            "hw_version": device.hw_version,
            "supported_capabilities": list(device.supported_capabilities),
            "available": device.available,
            "properties_data": device_properties,
            "state_data": device.get_state_data(),
        }

    # Collect query responses for each device
    for device_id, device in coordinator.devices.items():
        try:
            device_query_data = await api.query_device(device_id)
            query_data[device_id] = device_query_data
        except ValueError as err:
            query_data[device_id] = {"error": str(err)}
        except ConnectionError as err:
            query_data[device_id] = {"error": f"Connection error: {err!s}"}
        except TimeoutError as err:
            query_data[device_id] = {"error": f"Timeout error: {err!s}"}

    # Build diagnostics data
    return {
        "config_entry": async_redact_data(entry.as_dict(), REDACT_KEYS),
        "coordinator_data": {
            "last_update_success": coordinator.last_update_success,
            "device_count": len(coordinator.devices),
        },
        "devices": async_redact_data(device_data, REDACT_KEYS),
        "discovery_data": async_redact_data(discovery_data, REDACT_KEYS),
        "query_data": async_redact_data(query_data, REDACT_KEYS),
    }
