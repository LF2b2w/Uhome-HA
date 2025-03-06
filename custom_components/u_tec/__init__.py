"""The Uhome integration."""

from __future__ import annotations

from utec_py.api import UHomeApi

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import aiohttp_client, config_entry_oauth2_flow
from homeassistant.const import CONF_CLIENT_ID, CONF_CLIENT_SECRET

from . import api
from .const import DOMAIN, OAUTH2_AUTHORIZE, OAUTH2_TOKEN
from .coordinator import UhomeDataUpdateCoordinator

_PLATFORMS: list[Platform] = [Platform.LOCK, Platform.LIGHT, Platform.SWITCH]

# type UhomeConfigEntry = ConfigEntry[api.AsyncConfigEntryAuth]

async def async_setup(hass: HomeAssistant, config):
    """Set up the Uhome component."""
    hass.data.setdefault(DOMAIN, {})
    return True

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Uhome from a config entry."""
    config_entry_oauth2_flow.register_oauth2_implementation(
        hass,
        DOMAIN,
        config_entry_oauth2_flow.LocalOAuth2Implementation(
            hass,
            DOMAIN,
            entry.data[CONF_CLIENT_ID],
            entry.data[CONF_CLIENT_SECRET],
            OAUTH2_AUTHORIZE,
            OAUTH2_TOKEN,
        ),
    )
    implementation = (
        await config_entry_oauth2_flow.async_get_config_entry_implementation(
            hass, entry
        )
    )

    session = config_entry_oauth2_flow.OAuth2Session(hass, entry, implementation)

    auth_data = api.AsyncConfigEntryAuth(
        aiohttp_client.async_get_clientsession(hass), session
    )

    Uhomeapi = UHomeApi(auth_data)

    coordinator = UhomeDataUpdateCoordinator(hass, Uhomeapi)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "api": Uhomeapi,
        "coordinator": coordinator,
        "auth_data": auth_data,
    }

    await hass.config_entries.async_forward_entry_setups(entry, _PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, _PLATFORMS)
