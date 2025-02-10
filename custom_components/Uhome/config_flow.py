"""Config flow for testOauth2."""

import logging

from utec_py.api import UHomeApi
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_CLIENT_ID, CONF_CLIENT_SECRET
from homeassistant.core import _LOGGER, HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_entry_oauth2_flow
from homeassistant.util import Mapping

from .const import (
    CONF_API_SCOPE,
    DEFAULT_API_SCOPE,
    DOMAIN,
    OAUTH2_AUTHORIZE,
    OAUTH2_TOKEN,
)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_CLIENT_ID): str,
        vol.Required(CONF_CLIENT_SECRET): str,
        vol.Optional(CONF_API_SCOPE, default=DEFAULT_API_SCOPE): str,
    }
)


class UhomeOAuth2FlowHandler(
    config_entry_oauth2_flow.AbstractOAuth2FlowHandler, domain=DOMAIN
):
    """Config flow to handle Uhome OAuth2 authentication."""

    DOMAIN = DOMAIN
    VERSION = 1

    def __init__(self) -> None:
        """Initialize Uhome OAuth2 flow."""
        super().__init__()
        self._client_id: str | None
        self._client_secret: str | None
        self._api_scope: str | None

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
            # Save client credentials and api_scope to be used later.
            await self.async_set_unique_id(user_input["client_id"])
            self._abort_if_unique_id_configured()

            self._client_id = user_input[CONF_CLIENT_ID]
            self._client_secret = user_input[CONF_CLIENT_SECRET]
            self._api_scope = user_input.get(CONF_API_SCOPE, DEFAULT_API_SCOPE)

            self.logger.debug(
                "Retrieved client credentials, starting oauth authentication"
            )

            # Store client credentials for later use
            self.async_register_implementation(
                self.hass,
                await self._get_oauth2_implementation(),
            )

            return await self.async_step_pick_implementation()

        return self.async_show_form(step_id="user", data_schema=STEP_USER_DATA_SCHEMA)

    async def _get_oauth2_implementation(
        self,
    ) -> config_entry_oauth2_flow.LocalOAuth2Implementation:
        """Get OAuth2 implementation."""
        return config_entry_oauth2_flow.LocalOAuth2Implementation(
            self.hass,
            DOMAIN,
            self._client_id,
            self._client_secret,
            OAUTH2_AUTHORIZE,
            OAUTH2_TOKEN,
        )

    async def async_oauth_create_entry(
        self, data: dict[str, vol.Any]
    ) -> config_entries.FlowResult:
        """Create the config entry after successful OAuth2 authentication."""
        self.logger.debug(
            "Registering OAuth2 implementation with client_id=%s and client_secret=%s",
            self._client_id,
            self._client_secret,
        )
        return self.async_create_entry(
            title="Uhome Integration",
            data={
                "auth_implementation": DOMAIN,
                "token": data["token"],
                "client_id": self._client_id,
                "client_secret": self._client_secret,
                "api_scope": self._api_scope,
            },
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Get the options flow for this handler."""
        return OptionsFlowHandler()

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

    async def async_migrate_entry(self, hass: HomeAssistant, config_entry: ConfigEntry):
        """Migrate old entry."""
        _LOGGER.debug(
            "Migrating configuration from version %s.%s",
            config_entry.version,
            config_entry.minor_version,
        )

        if config_entry.version > 1:
            # This means the user has downgraded from a future version
            return False

        if config_entry.version == 1:
            pass

            # new_data = {**config_entry.data}
            # if config_entry.minor_version < 2:
            # modify Config Entry data with changes in version 1.2
            #    pass
            # if config_entry.minor_version < 3:
            # modify Config Entry data with changes in version 1.3
            #    pass

            # hass.config_entries.async_update_entry(config_entry, data=new_data, minor_version=3, version=1)

        _LOGGER.debug(
            "Migration to configuration version %s.%s successful",
            config_entry.version,
            config_entry.minor_version,
        )

        return True


class OptionsFlowHandler(OptionsFlow):
    """Handle options flow for Uhome integration."""

    def __init__(self) -> None:
        """Initialize options flow."""
        self.api: UHomeApi = None
        self.devices: dict[str, vol.Any] = {}

    async def async_step_init(
        self, user_input: dict[str, vol.Any] | None
    ) -> FlowResult:
        """Manage options."""
        errors = {}

        # Get API instance from Home Assistant
        self.api = self.hass.data[DOMAIN][self.config_entry.entry_id]

        if user_input is not None:
            # Combine the selected devices with the API scope
            options_data = {
                "selected_devices": user_input.get("selected_devices", []),
                CONF_API_SCOPE: user_input.get(CONF_API_SCOPE, DEFAULT_API_SCOPE),
            }
            return self.async_create_entry(title="", data=options_data)

        try:
            # Fetch available devices from the API
            response = await self.api.discover_devices()
            if "payload" in response:
                self.devices = {
                    device[
                        "id"
                    ]: f"{device.get('name', 'Unknown')} ({device.get('category', 'unknown')})"
                    for device in response["payload"].get("devices", [])
                }
        except (ValueError, TypeError):
            errors["base"] = "cannot_connect"
            self.devices = {}

        # Get currently selected devices from options
        selected_devices = self.config_entry.options.get("selected_devices", [])

        # Create the options form schema
        options_schema = {
            vol.Optional(
                "selected_devices", default=selected_devices
            ): vol.MultipleSelect(self.devices),
            vol.Optional(
                CONF_API_SCOPE,
                default=self.config_entry.options.get(
                    CONF_API_SCOPE, DEFAULT_API_SCOPE
                ),
            ): str,
        }

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(options_schema),
            errors=errors,
        )


class InvalidAuth(HomeAssistantError):
    """Error to indicate there is invalid auth."""
