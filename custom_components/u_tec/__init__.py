"""The Uhome integration."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import aiohttp_client, config_entry_oauth2_flow
from utec_py.api import UHomeApi

from . import api
from .const import CONF_PUSH_DEVICES, CONF_PUSH_ENABLED, DOMAIN
from .coordinator import UhomeDataUpdateCoordinator

_PLATFORMS: list[Platform] = [
    Platform.LOCK,
    Platform.LIGHT,
    Platform.SWITCH,
    Platform.SENSOR,
]

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Uhome from a config entry."""
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
    _LOGGER.debug("First Refresh Completed")

    # Initialize webhook handler
    webhook_handler = api.AsyncPushUpdateHandler(hass, Uhomeapi, entry.entry_id)
    _LOGGER.debug("Webhook handler initialised")

    # Check if push notifications are enabled in options
    push_enabled = entry.options.get(CONF_PUSH_ENABLED, True)
    push_devices = entry.options.get(CONF_PUSH_DEVICES, [])

    # Set push devices in coordinator
    coordinator.push_devices = push_devices

    # Register webhook if push is enabled
    if push_enabled:
        _LOGGER.debug("Push updates enabled")
        await webhook_handler.async_register_webhook(auth_data)
        _LOGGER.debug("Webhook registered complete")

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "api": Uhomeapi,
        "coordinator": coordinator,
        "auth_data": auth_data,
        "webhook_handler": webhook_handler,
    }

    await hass.config_entries.async_forward_entry_setups(entry, _PLATFORMS)
    # Unload the entry if the user disables push notifications
    entry.async_on_unload(entry.add_update_listener(async_update_options))
    # Unregister the webhook when the entry is unloaded
    entry.async_on_unload(webhook_handler.unregister_webhook)

    return True


async def async_update_options(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update."""
    # Get the webhook handler and coordinator
    webhook_handler = hass.data[DOMAIN][entry.entry_id]["webhook_handler"]
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    auth_data = hass.data[DOMAIN][entry.entry_id]["auth_data"]

    # Check if push notification setting has changed
    old_push_enabled = entry.data.get("options", {}).get(CONF_PUSH_ENABLED, True)
    new_push_enabled = entry.options.get(CONF_PUSH_ENABLED, True)

    # Update push devices in coordinator
    coordinator.push_devices = entry.options.get(CONF_PUSH_DEVICES, [])

    # Handle webhook registration/unregistration if needed
    if old_push_enabled != new_push_enabled:
        if new_push_enabled:
            # Register webhook
            await webhook_handler.async_register_webhook(auth_data)
        else:
            # Unregister webhook
            webhook_handler.unregister_webhook()
    await hass.config_entries.async_reload(entry.entry_id)
