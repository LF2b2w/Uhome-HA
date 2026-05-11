"""The Uhome integration."""

from __future__ import annotations

import logging

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_CLIENT_ID, CONF_CLIENT_SECRET, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import aiohttp_client, config_entry_oauth2_flow
import homeassistant.helpers.config_validation as cv
from utec_py.api import UHomeApi

from . import api
from .const import (
    CONF_DISCOVERY_INTERVAL,
    CONF_PUSH_DEVICES,
    CONF_PUSH_ENABLED,
    CONF_SCAN_INTERVAL,
    DEFAULT_DISCOVERY_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)
from .coordinator import UhomeDataUpdateCoordinator

_PLATFORMS: list[Platform] = [
    Platform.LOCK,
    Platform.LIGHT,
    Platform.SWITCH,
    Platform.SENSOR,
]

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema(
            {
                vol.Optional(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL): vol.All(
                    cv.positive_int, vol.Range(min=1)
                ),
                vol.Optional(CONF_DISCOVERY_INTERVAL, default=DEFAULT_DISCOVERY_INTERVAL): vol.All(
                    cv.positive_int, vol.Range(min=10)
                ),
            }
        )
    },
    extra=vol.ALLOW_EXTRA,
)

# Key used inside hass.data[DOMAIN] for yaml-sourced config (separate from entry IDs).
_YAML_CONFIG_KEY = "_yaml_config"


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Read configuration.yaml settings and store for use by config entries."""
    hass.data.setdefault(DOMAIN, {})
    if DOMAIN in config:
        hass.data[DOMAIN][_YAML_CONFIG_KEY] = config[DOMAIN]
        _LOGGER.debug(
            "Loaded u_tec config from configuration.yaml: scan_interval=%s, discovery_interval=%s",
            config[DOMAIN].get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
            config[DOMAIN].get(CONF_DISCOVERY_INTERVAL, DEFAULT_DISCOVERY_INTERVAL),
        )
    return True


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

    # Pick up any overrides from configuration.yaml, falling back to defaults.
    yaml_config = hass.data.get(DOMAIN, {}).get(_YAML_CONFIG_KEY, {})
    scan_interval = yaml_config.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
    discovery_interval = yaml_config.get(CONF_DISCOVERY_INTERVAL, DEFAULT_DISCOVERY_INTERVAL)

    coordinator = UhomeDataUpdateCoordinator(
        hass,
        Uhomeapi,
        config_entry=entry,
        scan_interval=scan_interval,
        discovery_interval=discovery_interval,
    )

    # Initial discovery populates self.devices before the first state poll.
    await coordinator.async_discover_devices()
    _LOGGER.debug("Initial device discovery complete")

    await coordinator.async_config_entry_first_refresh()
    _LOGGER.debug("First Refresh Completed")

    # Periodic re-discovery runs on a long interval to pick up added/removed devices.
    await coordinator.async_start_periodic_discovery()

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
    # Stop periodic discovery when the entry is unloaded
    entry.async_on_unload(coordinator.async_stop_periodic_discovery)

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


async def async_migrate_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Migrate old config entries to current version."""
    _LOGGER.debug(
        "Migrating u_tec config entry from %s.%s to 2.2",
        config_entry.version,
        config_entry.minor_version,
    )
    if config_entry.version < 2:
        new_data = {**config_entry.data}
        new_data.pop(CONF_CLIENT_SECRET, None)
        new_data.pop(CONF_CLIENT_ID, None)
        hass.config_entries.async_update_entry(
            config_entry, data=new_data, version=2, minor_version=1
        )
        _LOGGER.info("Migrated u_tec config entry to version 2.1")

    if config_entry.version == 2 and config_entry.minor_version < 2:
        await _migrate_auth_implementation_to_canonical(hass, config_entry)
        hass.config_entries.async_update_entry(config_entry, minor_version=2)
        _LOGGER.info("Migrated u_tec config entry to version 2.2")

    return True


async def _migrate_auth_implementation_to_canonical(
    hass: HomeAssistant, config_entry: ConfigEntry
) -> None:
    """Re-key legacy credentials to use the canonical auth_domain.

    Pre-fix entries created by the original config flow set
    ``data["auth_implementation"]`` to the credential's item_id
    (e.g. ``u_tec.<client_id>``) and the stored credential defaults
    ``auth_domain`` to that same item_id. The new flow always references the
    canonical ``u_tec`` auth_domain. Without this migration, rotating the
    credential through Reconfigure/Reauth on a legacy entry hits HA's safety
    check in ``async_delete_item`` (refuses to delete a credential still
    referenced by ``auth_implementation``) and silently no-ops the rotation.
    """
    # Local imports to avoid a hard import-time dependency on application_credentials.
    from homeassistant.components.application_credentials import (
        CONF_AUTH_DOMAIN,
        CONF_CLIENT_ID,
        CONF_CLIENT_SECRET,
        CONF_DOMAIN,
        DATA_COMPONENT,
        ClientCredential,
        async_import_client_credential,
    )

    current_impl = config_entry.data.get("auth_implementation")
    if current_impl == DOMAIN:
        return

    storage = hass.data.get(DATA_COMPONENT)
    legacy_cred: dict | None = None
    if storage is not None:
        for item in storage.async_items():
            if item.get(CONF_DOMAIN) != DOMAIN:
                continue
            if item["id"] == current_impl:
                legacy_cred = item
                break

    # Point the entry at the canonical auth_domain BEFORE touching storage so
    # async_delete_item's "still in use" guard no longer fires.
    hass.config_entries.async_update_entry(
        config_entry,
        data={**config_entry.data, "auth_implementation": DOMAIN},
    )

    if storage is None or legacy_cred is None:
        return

    if legacy_cred.get(CONF_AUTH_DOMAIN) == DOMAIN:
        return

    client_id = legacy_cred[CONF_CLIENT_ID]
    client_secret = legacy_cred[CONF_CLIENT_SECRET]
    try:
        await storage.async_delete_item(legacy_cred["id"])
    except Exception as err:  # noqa: BLE001
        _LOGGER.warning(
            "Could not delete legacy u_tec credential %s during migration",
            legacy_cred["id"],
            exc_info=err,
        )
        return

    await async_import_client_credential(
        hass, DOMAIN, ClientCredential(client_id, client_secret), DOMAIN
    )
