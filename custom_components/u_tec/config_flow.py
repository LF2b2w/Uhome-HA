"""Config flow for Uhome."""

import logging

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_CLIENT_ID, CONF_CLIENT_SECRET
from homeassistant.core import _LOGGER, HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_entry_oauth2_flow
from homeassistant.components.application_credentials import ClientCredential
import homeassistant.helpers.config_validation as cv
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
        #vol.Required(CONF_CLIENT_ID): str,
        #vol.Required(CONF_CLIENT_SECRET): str,
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
        #self._client_id = None
        #self._client_secret = None
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
            self.data=user_input
            return await self.async_step_pick_implementation()
        #return await super().async_step_user
        
        errors={}

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors
        )
            # Save client credentials and api_scope to be used later.
            #await self.async_set_unique_id(user_input[CONF_CLIENT_ID])
            #self._abort_if_unique_id_configured()

            #self._client_id = user_input[CONF_CLIENT_ID]
            #self._client_secret = user_input[CONF_CLIENT_SECRET]
            #self._api_scope = user_input.get(CONF_API_SCOPE, DEFAULT_API_SCOPE)

            #self.logger.debug(
            #    "Retrieved client credentials, starting oauth authentication"
            #)

            # Store client credentials in the flow data for later use
            #self.data = {
            #    "client_id": self._client_id,
            #    "client_secret": self._client_secret,
            #    "api_scope": self._api_scope,
            #}

            # Create and register the implementation
            #self.flow_impl = config_entry_oauth2_flow.LocalOAuth2Implementation(
            #    self.hass,
            #    DOMAIN,
            #    self._client_id,
            #    self._client_secret,
            #    OAUTH2_AUTHORIZE,
            #    OAUTH2_TOKEN,
            #)

            # Register the implementation
            #self.async_register_implementation(
            #    self.hass,
            #    self.flow_impl,
            #)

            

        #return self.async_show_form(step_id="user", data_schema=STEP_USER_DATA_SCHEMA)

    async def async_oauth_create_entry(
        self, data: dict[str, vol.Any]
    ) -> config_entries.FlowResult:
        """Create the config entry after successful OAuth2 authentication."""
        self.logger.debug(
            "Creating OAuth2 config entry for u-tec",)
        await self.hass.async_add_executor_job(
            self.hass.data["application_credentials"].async_client_credentials,
            DOMAIN,
            #ClientCredential(
            #    self._client_id,
            #    self._client_secret
            #)
        )

        return self.async_create_entry(
            title="Uhome Integration",
            data={
                "auth_implementation": DOMAIN,
                "token": data["token"],
                "api_scope": self.data[CONF_API_SCOPE],
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

class OptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options flow with proper device discovery."""
    def __init__(self, config_entry: ConfigEntry) -> None:
        self.config_entry = config_entry
        self.api = None
        self.devices = {}

    async def async_step_init(self, user_input=None) -> ConfigFlowResult:
        """Initialize options flow."""
        try:
            self.api = self.hass.data[DOMAIN][self.config_entry.entry_id]["api"]
            response = await self.api.discover_devices()
            self.devices = {
                device["id"]: f"{device.get('name', 'Unknown')} ({device.get('category', 'unknown')})"
                for device in response.get("payload", {}).get("devices", [])
            }
        except Exception as err:
            return self.async_abort(reason=f"discovery_failed: {err}")

        return await self.async_step_device_selection()

    async def async_step_device_selection(self, user_input=None) -> ConfigFlowResult:
        """Handle device selection."""
        current_selection = self.config_entry.options.get("devices", [])

        if user_input:
            return self.async_create_entry(
                title="",
                data={"devices": user_input["selected_devices"]}
            )

        return self.async_show_form(
            step_id="device_selection",
            data_schema=vol.Schema({
                vol.Optional(
                    "selected_devices",
                    default=current_selection
                ): cv.multi_select(self.devices)
            })
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
            config_entry,
            data=new_data,
            version=2,
            minor_version=1
        )
    return True