"""The U-tec Integration."""
import asyncio
from typing import Dict, Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.const import Platform
from homeassistant.exceptions import ConfigEntryNotReady

from .const import DOMAIN
from .discovery.auth import UtecApiClient

PLATFORMS: list[Platform] = []

async def async_setup(hass: HomeAssistant, config: Dict[str, Any]) -> bool:
    """Set up the U-tec component."""
    hass.data.setdefault(DOMAIN, {})
    return True

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up U-tec from a config entry."""
    try:
        # Initialize API client with stored credentials
        client = UtecApiClient(
            entry.data["client_id"],
            entry.data["client_secret"],
            entry.data.get("access_token")
        )

        # Store the client instance
        hass.data[DOMAIN][entry.entry_id] = client

        # Set up platforms
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

        # Register update listener for config entry changes
        entry.async_on_unload(entry.add_update_listener(update_listener))

        return True

    except Exception as err:
        raise ConfigEntryNotReady from err

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    # Unload platforms
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        # Remove client instance
        client = hass.data[DOMAIN].pop(entry.entry_id)
        await client.close()

    return unload_ok

async def update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update."""
    await hass.config_entries.async_reload(entry.entry_id)