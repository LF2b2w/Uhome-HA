"""Config flow for Uhome."""

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry, ConfigFlowResult
from homeassistant.const import CONF_CLIENT_ID, CONF_CLIENT_SECRET
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import config_entry_oauth2_flow, selector
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.selector import (
    BooleanSelector,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)
from homeassistant.util import Mapping

from utec_py.devices.light import Light as UhomeLight
from utec_py.devices.lock import Lock as UhomeLock
from utec_py.devices.switch import Switch as UhomeSwitch

from .const import (
    CONF_API_SCOPE,
    CONF_HA_DEVICES,
    CONF_OPTIMISTIC_LIGHTS,
    CONF_OPTIMISTIC_LOCKS,
    CONF_OPTIMISTIC_SWITCHES,
    CONF_PUSH_DEVICES,
    CONF_PUSH_ENABLED,
    DEFAULT_API_SCOPE,
    DOMAIN,
)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        # vol.Required(CONF_CLIENT_ID): str,
        # vol.Optional(CONF_PUSH_ENABLED, default="push_enabled"): BooleanSelector(),
        vol.Optional(CONF_API_SCOPE, default=DEFAULT_API_SCOPE): str,
    }
)


OPTIMISTIC_MODE_ALL = "all"
OPTIMISTIC_MODE_NONE = "none"
OPTIMISTIC_MODE_CUSTOM = "custom"
OPTIMISTIC_MODES = [OPTIMISTIC_MODE_ALL, OPTIMISTIC_MODE_NONE, OPTIMISTIC_MODE_CUSTOM]


def _current_mode(value):
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

    def __init__(self) -> None:
        """Initialize Uhome OAuth2 flow."""
        super().__init__()
        self._api_scope = None
        self.data = {}

    @property
    def logger(self) -> logging.Logger:
        """Return logger."""
        return _LOGGER

    @property
    def extra_authorize_data(self) -> dict[str, Any]:
        """Extra data that needs to be appended to the authorize url."""
        return {"scope": self._api_scope or DEFAULT_API_SCOPE}

    async def async_step_user(self, user_input=None) -> ConfigFlowResult:
        """Prompt the user to enter their client credentials and API scope."""
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")

        if user_input is not None:
            self.data = user_input
            return await self.async_step_pick_implementation()

        errors = {}

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
        )

    async def async_oauth_create_entry(
        self, data: dict
    ) -> config_entries.ConfigFlowResult:
        """Create an entry for the flow.

        Ok to override if you want to fetch extra info or even add another step.
        """
        options = {
            CONF_PUSH_ENABLED: True,
            CONF_PUSH_DEVICES: [],  # Empty list means all devices
            CONF_HA_DEVICES: [],
        }
        return self.async_create_entry(
            title=self.flow_impl.name, data=data, options=options
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, vol.Any]
    ) -> ConfigFlowResult:
        """Perform reauth upon migration of old entries."""
        return await self.async_step_reauth_confirm(entry_data)

    async def async_step_reauth_confirm(
        self, user_input: Mapping[str, vol.Any] | None = None
    ) -> ConfigFlowResult:
        """Dialog that informs the user that reauth is required."""
        if user_input is None:
            return self.async_show_form(
                step_id="reauth_confirm",
                data_schema=vol.Schema({}),
            )
        return await self.async_step_user()

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
        device_cls: type,
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



