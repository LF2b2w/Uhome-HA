"""The U-tec Integration."""
import asyncio
from typing import Dict, Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_entry_oauth2_flow
from homeassistant.const import CONF_CLIENT_ID, CONF_CLIENT_SECRET

from .const import DOMAIN, CONF_SCOPE
from .api import UtecApiClient

async def async_setup(hass: HomeAssistant, config: Dict[str, Any]) -> bool:
    """Set up the U-tec component."""
    hass.data[DOMAIN] = {}
    return True

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up U-tec from a config entry."""
    implementation = await config_entry_oauth2_flow.async_get_config_entry_implementation(
        hass, entry
    )

    oauth_session = config_entry_oauth2_flow.OAuth2Session(
        hass, entry, implementation
    )

    client = UtecApiClient(
        entry.data[CONF_CLIENT_ID],
        entry.data[CONF_CLIENT_SECRET],
        oauth_session,
    )

    hass.data[DOMAIN][entry.entry_id] = client

    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if DOMAIN in hass.data:
        client = hass.data[DOMAIN].pop(entry.entry_id)
        await client.close()

    return True