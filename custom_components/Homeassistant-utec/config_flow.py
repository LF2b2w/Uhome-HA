"""Config flow for U-tec Integration."""
import logging
from typing import Any, Dict, Optional
from urllib.parse import urlencode
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import config_entry_oauth2_flow
from homeassistant.data_entry_flow import FlowResult

from .const import (
    DOMAIN,
    CONF_CLIENT_ID,
    CONF_CLIENT_SECRET,
    CONF_SCOPE,
    DEFAULT_SCOPE,
    OAUTH2_AUTHORIZE,
    OAUTH2_TOKEN,
)

class UtecOAuth2FlowHandler(
    config_entry_oauth2_flow.AbstractOAuth2FlowHandler, domain=DOMAIN
):
    """Handle U-tec OAuth2 config flow."""

    DOMAIN = DOMAIN
    VERSION = 1

    @property
    def logger(self):
        """Return logger."""
        return logging.getLogger(__name__)

    async def async_step_user(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> FlowResult:
        """Handle a flow initialized by the user."""
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")

        if user_input is None:
            return self.async_show_form(
                step_id="user",
                data_schema=vol.Schema(
                    {
                        vol.Required(CONF_CLIENT_ID): str,
                        vol.Required(CONF_CLIENT_SECRET): str,
                        vol.Optional(CONF_SCOPE, default=DEFAULT_SCOPE): str,
                    }
                ),
            )

        self.client_id = user_input[CONF_CLIENT_ID]
        self.client_secret = user_input[CONF_CLIENT_SECRET]
        self.scope = user_input.get(CONF_SCOPE, DEFAULT_SCOPE)

        return await self.async_step_auth()

    async def async_oauth_create_entry(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Create an oauth config entry or update existing entry for reauth."""
        data[CONF_CLIENT_ID] = self.client_id
        data[CONF_CLIENT_SECRET] = self.client_secret
        data[CONF_SCOPE] = self.scope

        existing_entry = await self.async_set_unique_id(DOMAIN)
        if existing_entry:
            self.hass.config_entries.async_update_entry(existing_entry, data=data)
            await self.hass.config_entries.async_reload(existing_entry.entry_id)
            return self.async_abort(reason="reauth_successful")

        return self.async_create_entry(title="U-tec Integration", data=data)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Get the options flow for this handler."""
        return OptionsFlowHandler(config_entry)

    @property
    def oauth_authorization_url(self) -> str:
        """Generate the OAuth2 authorization URL."""
        params = {
            "response_type": "code",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "scope": self.scope,
            "redirect_uri": self.redirect_uri,
            "state": self.flow_id,
        }
        return f"{OAUTH2_AUTHORIZE}?{urlencode(params)}"