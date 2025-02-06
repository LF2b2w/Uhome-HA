"""The Uhome-HA integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import aiohttp_client, config_entry_oauth2_flow

from . import api
from .const import DOMAIN
from .coordinator import UHomeDeviceCoordinator

_PLATFORMS: list[Platform] = [
    Platform.LIGHT,
    Platform.SWITCH,
    Platform.LOCK,
    Platform.SENSOR,
]

type UhomeConfigEntry = ConfigEntry[api.AsyncConfigEntryAuth]


# async def async_setup(hass: HomeAssistant, config: UhomeConfigEntry) -> bool:
#    """Set up the Utec component."""
#    hass.data[DOMAIN] = {}
#    return True


async def async_setup_entry(hass: HomeAssistant, entry: UhomeConfigEntry) -> bool:
    """Set up Uhome-HA from a config entry."""
    implementation = (
        await config_entry_oauth2_flow.async_get_config_entry_implementation(
            hass, entry
        )
    )

    session = config_entry_oauth2_flow.OAuth2Session(hass, entry, implementation)
    # api = UhomeApiWrapper(hass, session, entry.data["token"])

    # If using an aiohttp-based API lib
    entry.runtime_data = api.AsyncConfigEntryAuth(
        aiohttp_client.async_get_clientsession(hass), session
    )

    coordinator = UHomeDeviceCoordinator(hass, api)
    await coordinator.async_config_entry_first_refresh()

    hass.data[DOMAIN][entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, _PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, _PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok
