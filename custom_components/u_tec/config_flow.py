"""Config flow for Uhome."""

from collections.abc import Mapping
import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.components.application_credentials import (
    ClientCredential,
    CONF_CLIENT_ID as APP_CREDS_CLIENT_ID,
    CONF_DOMAIN as APP_CREDS_DOMAIN,
    CONF_ID as APP_CREDS_ID,
    DATA_COMPONENT as APP_CREDS_DATA,
    async_import_client_credential,
)
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlowResult,
    SOURCE_REAUTH,
    SOURCE_RECONFIGURE,
)
from homeassistant.core import callback
from homeassistant.helpers import config_entry_oauth2_flow
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.selector import (
    BooleanSelector,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from utec_py.devices.device import BaseDevice
from utec_py.devices.light import Light as UhomeLight
from utec_py.devices.lock import Lock as UhomeLock
from utec_py.devices.switch import Switch as UhomeSwitch

from .const import (
    CONF_HA_DEVICES,
    CONF_OPTIMISTIC_LIGHTS,
    CONF_OPTIMISTIC_LOCKS,
    CONF_OPTIMISTIC_SWITCHES,
    CONF_PUSH_DEVICES,
    CONF_PUSH_ENABLED,
    DEFAULT_API_SCOPE,
    DOMAIN,
    OAUTH2_AUTHORIZE,
    OAUTH2_TOKEN,
)


OPTIMISTIC_MODE_ALL = "all"
OPTIMISTIC_MODE_NONE = "none"
OPTIMISTIC_MODE_CUSTOM = "custom"
OPTIMISTIC_MODES = [OPTIMISTIC_MODE_ALL, OPTIMISTIC_MODE_NONE, OPTIMISTIC_MODE_CUSTOM]


def _current_mode(value: bool | list[str] | None) -> str:
    """Infer the mode selector default from a stored option value."""
    if value is True or value is None:
        return OPTIMISTIC_MODE_ALL
    if value is False:
        return OPTIMISTIC_MODE_NONE
    return OPTIMISTIC_MODE_CUSTOM


_LOGGER = logging.getLogger(__name__)


class UhomeOAuth2FlowHandler(
    config_entry_oauth2_flow.AbstractOAuth2FlowHandler, domain=DOMAIN
):
    """Config flow to handle Uhome OAuth2 authentication."""

    DOMAIN = DOMAIN
    VERSION = 2
    MINOR_VERSION = 2

    def __init__(self) -> None:
        """Initialize Uhome OAuth2 flow."""
        super().__init__()
        self._pending_credential: ClientCredential | None = None

    @property
    def logger(self) -> logging.Logger:
        """Return logger."""
        return _LOGGER

    @property
    def extra_authorize_data(self) -> dict[str, Any]:
        """Extra data that needs to be appended to the authorize url."""
        return {"scope": DEFAULT_API_SCOPE}

    async def async_step_user(self, user_input=None) -> ConfigFlowResult:
        """Entry point for initial setup.

        Always renders the credential form (blank or prefilled from any existing
        application_credentials entry) — bypasses HA's stock "missing_credentials"
        prompt entirely so the user only ever sees one credential form per setup.
        """
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")
        return await self.async_step_replace_credentials()

    def _get_existing_credential(self) -> dict | None:
        """Return the first stored credential dict for this domain, or None."""
        storage = self.hass.data.get(APP_CREDS_DATA)
        if storage is None:
            return None
        for item in storage.async_items():
            if item.get(APP_CREDS_DOMAIN) == DOMAIN:
                return item
        return None

    async def async_step_replace_credentials(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Render the credential form and start OAuth with an in-memory implementation.

        Used by initial setup (via async_step_user), issue #50 recovery (stale creds
        in HA's app-creds store from a prior failed attempt), and reconfigure of a
        working entry (via async_step_reconfigure).

        The application_credentials store is NOT mutated here. We build an in-memory
        LocalOAuth2Implementation with the entered creds, set self.flow_impl directly,
        and jump to async_step_auth — bypassing async_step_pick_implementation. The
        actual store update happens in async_oauth_create_entry, on the OAuth-success
        path only. Consequence: if OAuth fails, any existing credential is untouched
        and a working config entry continues to refresh against valid creds.
        """
        if user_input is not None:
            client_id = (user_input.get("client_id") or "").strip()
            client_secret = (user_input.get("client_secret") or "").strip()

            if not client_id or not client_secret:
                return self._show_replace_form(
                    client_id=client_id,
                    errors={"base": "empty_credentials"},
                )

            self._pending_credential = ClientCredential(client_id, client_secret)
            self.flow_impl = config_entry_oauth2_flow.LocalOAuth2Implementation(
                self.hass,
                DOMAIN,
                client_id,
                client_secret,
                OAUTH2_AUTHORIZE,
                OAUTH2_TOKEN,
            )
            return await self.async_step_auth()

        return self._show_replace_form(client_id=None)

    def _show_replace_form(
        self,
        *,
        client_id: str | None,
        errors: dict[str, str] | None = None,
    ) -> ConfigFlowResult:
        """Render the replace-credentials form with optional prefill + errors."""
        if client_id is None:
            existing = self._get_existing_credential()
            client_id = existing.get(APP_CREDS_CLIENT_ID, "") if existing else ""

        return self.async_show_form(
            step_id="replace_credentials",
            data_schema=vol.Schema(
                {
                    vol.Required("client_id", default=client_id): str,
                    vol.Required("client_secret", default=""): str,
                }
            ),
            errors=errors or {},
        )

    async def async_oauth_create_entry(
        self, data: dict
    ) -> ConfigFlowResult:
        """Create or update the config entry depending on the flow source.

        If credentials were entered via async_step_replace_credentials and OAuth
        succeeded, commit them to the application_credentials store now and rewrite
        the entry's auth_implementation reference to the standard "u_tec" auth_domain
        (which is what async_get_implementations resolves against).
        """
        if self._pending_credential is not None:
            await self._commit_pending_credential()
            data = {**data, "auth_implementation": "u_tec"}

        if self.source == SOURCE_RECONFIGURE:
            entry = self._get_reconfigure_entry()
            return self.async_update_reload_and_abort(
                entry,
                data=data,
                options=dict(entry.options),
            )

        if self.source == SOURCE_REAUTH:
            entry = self._get_reauth_entry()
            return self.async_update_reload_and_abort(
                entry,
                data=data,
                options=dict(entry.options),
            )

        options = {
            CONF_PUSH_ENABLED: True,
            CONF_PUSH_DEVICES: [],  # Empty list means all devices
            CONF_HA_DEVICES: [],
        }
        # Static title — flow_impl.name is "Configuration.yaml" for the in-memory
        # LocalOAuth2Implementation built in async_step_replace_credentials, which
        # would surface as the entry title in the HA UI. Use the integration name.
        return self.async_create_entry(
            title="U-Tec", data=data, options=options
        )

    async def _commit_pending_credential(self) -> None:
        """Persist the deferred credential to the application_credentials store.

        Called from async_oauth_create_entry on the OAuth-success path. For items
        whose client_id matches the new one, delete BEFORE import — otherwise
        async_import_item is a no-op on duplicate suggested_id and the secret
        wouldn't rotate. Delete failures in that pre-import phase are therefore
        re-raised so the flow aborts instead of reporting a phantom success. For
        items with a different client_id, import first then delete: HA's
        async_delete_item refuses to delete a credential currently
        referenced by an entry's auth_implementation, but the new cred has the
        canonical auth_domain ("u_tec") so importing it first means the entry
        can resolve a valid implementation regardless of whether the legacy
        delete succeeds. (Legacy entries with auth_implementation pointing at
        a credential item_id are normalised to the canonical auth_domain by
        async_migrate_entry at integration setup, so by the time this runs the
        delete should not be blocked.)
        """
        assert self._pending_credential is not None  # guarded by caller
        new_client_id = self._pending_credential.client_id

        storage = self.hass.data.get(APP_CREDS_DATA)
        matching_ids: list[str] = []
        other_ids: list[str] = []
        if storage is not None:
            for item in storage.async_items():
                if item.get(APP_CREDS_DOMAIN) != DOMAIN:
                    continue
                if item.get(APP_CREDS_CLIENT_ID) == new_client_id:
                    matching_ids.append(item[APP_CREDS_ID])
                else:
                    other_ids.append(item[APP_CREDS_ID])

        for item_id in matching_ids:
            # Delete failure here cannot be swallowed: async_import_client_credential
            # is a no-op on duplicate suggested_id, so a leftover record means the
            # secret silently doesn't rotate while OAuth still reports success.
            try:
                await storage.async_delete_item(item_id)
            except Exception as err:  # noqa: BLE001
                _LOGGER.error(
                    "Aborting u_tec credential rotation: failed to delete pre-existing record %s",
                    item_id,
                    exc_info=err,
                )
                raise

        await async_import_client_credential(
            self.hass,
            DOMAIN,
            self._pending_credential,
            "u_tec",
        )

        if storage is not None:
            for item_id in other_ids:
                try:
                    await storage.async_delete_item(item_id)
                except Exception as err:  # noqa: BLE001
                    _LOGGER.warning(
                        "Failed to delete stale u_tec credential %s",
                        item_id,
                        exc_info=err,
                    )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Re-authenticate an existing entry.

        Dispatch directly to the credentials form — no confirmation step.
        The framework hands us the entry's data dict but we don't need it:
        the form prefills client_id from the application_credentials store,
        and OAuth-success updates the entry in async_oauth_create_entry.
        """
        return await self.async_step_replace_credentials()

    async def async_step_reconfigure(
        self, entry_data: Mapping[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Entry point when the user clicks Reconfigure on the integration card."""
        return await self.async_step_replace_credentials()

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Get the options flow for this handler."""
        return OptionsFlowHandler(config_entry)

class OptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options flow with proper device discovery."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Initialise OptionsFlowHandler."""
        super().__init__()
        self.api = None
        self.devices = {}
        self.options = dict(config_entry.options)
        self._pending_pickers: list[str] = []

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Initialize options flow."""
        return self.async_show_menu(
            step_id="init",
            menu_options={
                "update_push": "Update Push Status",
                "get_devices": "Select Active Devices",
                "optimistic_updates": "Configure Optimistic Updates",
            },
        )

    async def async_step_update_push(
        self,
        user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Select devices for push updates."""

        if user_input is not None:
            self.options[CONF_PUSH_ENABLED] = user_input[CONF_PUSH_ENABLED]

            if user_input[CONF_PUSH_ENABLED]:
                return await self.async_step_push_device_selection()

            return self.async_create_entry(title="", data=self.options)

        return self.async_show_form(
            step_id="update_push",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_PUSH_ENABLED,
                        default=self.options.get(CONF_PUSH_ENABLED, True),
                    ): BooleanSelector(),
                }
            ),
        )

    async def async_step_push_device_selection(
        self,
        user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle device selection step."""
        if user_input is not None:
            self.options[CONF_PUSH_DEVICES] = user_input[CONF_PUSH_DEVICES]
            return self.async_create_entry(title="", data=self.options)

        coordinator = self.hass.data[DOMAIN][self.config_entry.entry_id]["coordinator"]

        self.devices = {
            device_id: device.name for device_id, device in coordinator.devices.items()
        }

        # If no devices are selected, default to all devices
        selected_devices = self.options.get(CONF_PUSH_DEVICES, [])
        if not selected_devices:
            selected_devices = list(self.devices.keys())

        return self.async_show_form(
            step_id="push_device_selection",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_PUSH_DEVICES,
                        default=selected_devices,
                    ): vol.All(
                        cv.multi_select(self.devices),
                    ),
                }
            ),
            description_placeholders={
                "devices": ", ".join(self.devices.values()),
            },
        )

    async def async_step_optimistic_updates(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Configure optimistic updates per device type."""
        mode_selector = SelectSelector(
            SelectSelectorConfig(
                options=OPTIMISTIC_MODES,
                mode=SelectSelectorMode.DROPDOWN,
                translation_key="optimistic_mode",
            )
        )

        if user_input is not None:
            self._pending_pickers = []
            for conf_key, field in (
                (CONF_OPTIMISTIC_LIGHTS, "lights_mode"),
                (CONF_OPTIMISTIC_SWITCHES, "switches_mode"),
                (CONF_OPTIMISTIC_LOCKS, "locks_mode"),
            ):
                mode = user_input[field]
                if mode == OPTIMISTIC_MODE_ALL:
                    self.options[conf_key] = True
                elif mode == OPTIMISTIC_MODE_NONE:
                    self.options[conf_key] = False
                elif mode == OPTIMISTIC_MODE_CUSTOM:
                    self._pending_pickers.append(conf_key)
            return await self._advance_optimistic_picker()

        lights_default = _current_mode(self.options.get(CONF_OPTIMISTIC_LIGHTS))
        switches_default = _current_mode(self.options.get(CONF_OPTIMISTIC_SWITCHES))
        locks_default = _current_mode(self.options.get(CONF_OPTIMISTIC_LOCKS))

        return self.async_show_form(
            step_id="optimistic_updates",
            data_schema=vol.Schema(
                {
                    vol.Required("lights_mode", default=lights_default): mode_selector,
                    vol.Required("switches_mode", default=switches_default): mode_selector,
                    vol.Required("locks_mode", default=locks_default): mode_selector,
                }
            ),
        )

    async def _advance_optimistic_picker(self) -> ConfigFlowResult:
        """Dispatch to the next pending picker, or finalise."""
        if not self._pending_pickers:
            return self.async_create_entry(title="", data=self.options)
        next_key = self._pending_pickers[0]
        dispatch = {
            CONF_OPTIMISTIC_LIGHTS: self.async_step_pick_lights,
            CONF_OPTIMISTIC_SWITCHES: self.async_step_pick_switches,
            CONF_OPTIMISTIC_LOCKS: self.async_step_pick_locks,
        }
        return await dispatch[next_key]()

    async def _optimistic_picker_step(
        self,
        *,
        step_id: str,
        conf_key: str,
        device_cls: type[BaseDevice],
        user_input: dict[str, Any] | None,
    ) -> ConfigFlowResult:
        """Render / handle a device-picker step for one device type."""
        if user_input is not None:
            self.options[conf_key] = user_input[conf_key]
            self._pending_pickers.pop(0)
            return await self._advance_optimistic_picker()

        coordinator = self.hass.data[DOMAIN][self.config_entry.entry_id]["coordinator"]
        devices = {
            device_id: device.name
            for device_id, device in coordinator.devices.items()
            if isinstance(device, device_cls)
        }

        if not devices:
            # No devices of this type to pick from — skip to next picker.
            self.options[conf_key] = []
            self._pending_pickers.pop(0)
            return await self._advance_optimistic_picker()

        stored = self.options.get(conf_key)
        default = stored if isinstance(stored, list) else list(devices.keys())

        return self.async_show_form(
            step_id=step_id,
            data_schema=vol.Schema(
                {
                    vol.Required(conf_key, default=default): cv.multi_select(devices),
                }
            ),
        )

    async def async_step_pick_lights(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Pick which light devices are optimistic."""
        return await self._optimistic_picker_step(
            step_id="pick_lights",
            conf_key=CONF_OPTIMISTIC_LIGHTS,
            device_cls=UhomeLight,
            user_input=user_input,
        )

    async def async_step_pick_switches(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Pick which switch devices are optimistic."""
        return await self._optimistic_picker_step(
            step_id="pick_switches",
            conf_key=CONF_OPTIMISTIC_SWITCHES,
            device_cls=UhomeSwitch,
            user_input=user_input,
        )

    async def async_step_pick_locks(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Pick which lock devices are optimistic."""
        return await self._optimistic_picker_step(
            step_id="pick_locks",
            conf_key=CONF_OPTIMISTIC_LOCKS,
            device_cls=UhomeLock,
            user_input=user_input,
        )

    async def async_step_get_devices(
        self,
        user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Retrieve all devices from api."""
        try:
            self.api = self.hass.data[DOMAIN][self.config_entry.entry_id]["api"]
            response = await self.api.discover_devices()
            self.devices = {
                device[
                    "id"
                ]: f"{device.get('name', 'Unknown')} ({device.get('category', 'unknown')})"
                for device in response.get("payload", {}).get("devices", [])
            }
        except ValueError as err:
            return self.async_abort(reason=f"discovery_failed: {err}")

        return await self.async_step_device_selection(None)

    async def async_step_device_selection(self, user_input: None) -> ConfigFlowResult:
        """Handle device selection."""
        if not self.devices:
            _LOGGER.error("No devices found")
            return self.async_abort(reason="no devices found")
        # Get the current selection from the config entry options
        current_selection = self.config_entry.options.get("devices", [])

        if user_input is not None:
            return self.async_create_entry(
                title="", data={"devices": user_input["selected_devices"]}
            )

        # Show the device selection form
        return self.async_show_form(
            step_id="device_selection",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        "selected_devices",
                        default=current_selection,
                    ): cv.multi_select(self.devices)
                }
            ),
        )



