"""The Uhome integration."""

from __future__ import annotations

from utec_py.api import UHomeApi

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers import aiohttp_client, config_entry_oauth2_flow
from homeassistant.const import CONF_CLIENT_ID, CONF_CLIENT_SECRET

from . import api
from .const import DOMAIN, OAUTH2_AUTHORIZE, OAUTH2_TOKEN
from .coordinator import UhomeDataUpdateCoordinator

_PLATFORMS: list[Platform] = [Platform.LOCK, Platform.LIGHT, Platform.SWITCH]

# type UhomeConfigEntry = ConfigEntry[api.AsyncConfigEntryAuth]

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Uhome from a config entry."""
    implementation = (
        await config_entry_oauth2_flow.async_get_config_entry_implementation(
            hass, 
            entry
        )
    )

    session = config_entry_oauth2_flow.OAuth2Session(hass, entry, implementation)

    auth_data = api.AsyncConfigEntryAuth(
        aiohttp_client.async_get_clientsession(hass), session
    )

    #if not await auth_data.validate_credentials():
    #    raise ConfigEntryAuthFailed

    Uhomeapi = UHomeApi(auth_data)

    coordinator = UhomeDataUpdateCoordinator(hass, Uhomeapi)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "api": Uhomeapi,
        "coordinator": coordinator,
        "auth_data": auth_data,
    }

    await hass.config_entries.async_forward_entry_setups(entry, _PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(async_update_options))
    return True

async def async_update_options(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update."""
    await hass.config_entries.async_reload(entry.entry_id)

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, _PLATFORMS)
