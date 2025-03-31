"""Config flow for Uhome."""

import logging

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry, ConfigFlowResult
from homeassistant.const import CONF_CLIENT_ID, CONF_CLIENT_SECRET
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import config_entry_oauth2_flow
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.selector import BooleanSelector
from homeassistant.util import Mapping

from .const import (
    CONF_API_SCOPE,
    CONF_HA_DEVICES,
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


_LOGGER = logging.getLogger(__name__)

class UhomeOAuth2FlowHandler(
    config_entry_oauth2_flow.AbstractOAuth2FlowHandler, domain=DOMAIN
):
    """Config flow to handle Uhome OAuth2 authentication."""

    DOMAIN = DOMAIN
    VERSION = 1

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
    def extra_authorize_data(self) -> dict[str, vol.Any]:
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

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Get the options flow for this handler."""
        return OptionsFlowHandler(config_entry)

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


class OptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options flow with proper device discovery."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialise OptionsFlowHandler."""
        # self.config_entry = ConfigEntry
        self.api = None
        self.devices = {}
        self.config_entry = config_entry
        self.options = dict(config_entry.options)
    

    async def async_step_init(
        self, user_input: dict[str, any] | None = None
    ) -> ConfigFlowResult:
        """Initialize options flow."""
        return self.async_show_menu(
            step_id="init",
            menu_options=["update_push", "get_devices"],
            description_placeholders={"model": "Example"},
        )

    async def async_step_update_push(
        self, user_input: dict[str, any] | None = None
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
        self, user_input: dict[str, any] | None = None
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

    async def async_step_get_devices(
        self, user_input: dict[str, any] | None = None
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
        current_selection = self.config_entry.options.get("devices", [])
        if not current_selection:
            _LOGGER.error("No devices found")
            return self.async_abort(reason="no devices found")

        if user_input is not None:
            return self.async_create_entry(
                title="", data={"devices": user_input["selected_devices"]}
            )
        elif user_input is None:
            _LOGGER.error("No devices found")
            return self.async_abort(reason="no devices found")

        return self.async_show_form(
            step_id="device_selection",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        "Select devices you want to enable in HomeAssistant:",
                        default=current_selection,
                    ): cv.multi_select(self.devices)
                }
            ),
        )

    async def async_step_api_reauth_opt(self, user_input=None) -> ConfigFlowResult:
        """Handle API reauthentication option."""
        return await self.async_step_user()


async def async_migrate_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Migrate old config entries to current version."""
    if config_entry.version < 2:
        new_data = {**config_entry.data}
        # Remove raw secrets from legacy entries
        new_data.pop(CONF_CLIENT_SECRET, None)
        new_data.pop(CONF_CLIENT_ID, None)
        hass.config_entries.async_update_entry(
            config_entry, data=new_data, version=2, minor_version=1
        )
    return True
