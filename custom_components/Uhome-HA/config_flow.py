"""Config flow for Utec integration."""

from collections.abc import Mapping
import logging
from typing import Any

import voluptuous as vol

from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_entry_oauth2_flow
from homeassistant.helpers.discovery_flow import ConfigFlowResult

from .const import (
    CONF_API_SCOPE,
    CONF_CLIENT_ID,
    CONF_CLIENT_SECRET,
    DOMAIN,
    OAUTH2_AUTHORIZE,
    OAUTH2_TOKEN,
)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_CLIENT_ID): str,
        vol.Required(CONF_CLIENT_SECRET): str,
        vol.Required(CONF_API_SCOPE): str,
    }
)


class UhomeHub:
    """Class to authenticate with the Uhome API."""

    def __init__(self, client_id: str, client_secret: str, api_scope: str) -> None:
        """Initialize."""
        self.client_id = client_id
        self.client_secret = client_secret
        self.api_scope = api_scope

    async def authenticate(self) -> bool:
        """Test if we can authenticate with the host."""
        return True


class UtecOAuth2FlowHandler(
    config_entry_oauth2_flow.AbstractOAuth2FlowHandler, domain=DOMAIN
):
    """Config flow to handle Utec OAuth2 authentication."""

    DOMAIN = DOMAIN
    VERSION = 1

    @property
    def logger(self):
        """Return logger."""
        return logging.getLogger(__name__)

    async def async_step_user(self, user_input=None) -> ConfigFlowResult:
        """Prompt the user to enter their client credentials and API scope."""
        if user_input is not None:
            # Save client credentials and api_scope to be used later.
            await self.async_set_unique_id(user_input["client_id"])
            self._abort_if_unique_id_configured()

            self.flow_impl = config_entry_oauth2_flow.LocalOAuth2Implementation(
                self.hass,
                DOMAIN,
                user_input["client_id"],
                user_input["client_secret"],
                OAUTH2_AUTHORIZE,
                OAUTH2_TOKEN,
                scope=user_input.get("scope", "all"),
            )

            return await self.async_step_pick_implementation()

        return self.async_show_form(step_id="user", data_schema=STEP_USER_DATA_SCHEMA)

    async def async_oauth_create_entry(self, data):
        """Create an entry after OAuth2 is complete."""
        return self.async_create_entry(title="Utec OAuth2", data=data)

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Perform reauth upon migration of old entries."""
        return await self.async_step_reauth_confirm(entry_data)

    async def async_step_reauth_confirm(
        self, user_input: Mapping[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Dialog that informs the user that reauth is required."""
        if user_input is None:
            return self.async_show_form(
                step_id="reauth_confirm",
                data_schema=vol.Schema({}),
            )

        return await self.async_step_user()


class InvalidAuth(HomeAssistantError):
    """Error to indicate there is invalid auth."""
