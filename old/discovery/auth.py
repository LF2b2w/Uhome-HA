# custom_components/utec/oauth2.py
"""OAuth2 implementation for U-Tec."""
from typing import Any, cast
import logging
from aiohttp import ClientSession
import voluptuous as vol
from py-Utec import AbstractAuth

from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_entry_oauth2_flow
from homeassistant.data_entry_flow import FlowResult
from homeassistant.const import CONF_CLIENT_ID, CONF_CLIENT_SECRET

from const import DOMAIN, AUTH_URL, TOKEN_URL

_LOGGER = logging.getLogger(__name__)

class AuthImpl(AbstractAuth):
    def __init__(self, websession: ClientSession, host: str, token_manager):
        super().__init__(websession, host)
        self.token_manager = TokenManager

    async def async_get_access_token(self) -> str:
        


class TokenManager:
    def __init__(self):


class UTecOAuth2Implementation(config_entry_oauth2_flow.LocalOAuth2Implementation):
    """OAuth2 implementation that only uses the external url."""

    def __init__(
        self,
        hass: HomeAssistant,
        domain: str,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
    ) -> None:
        """Initialize local auth implementation."""
        self._name = domain
        super().__init__(
            hass=hass,
            domain=domain,
            client_id=client_id,
            client_secret=client_secret,
            authorize_url=AUTH_URL,
            token_url=TOKEN_URL,
        )
        self.redirect_uri = redirect_uri

    @property
    def name(self) -> str:
        """Name of the implementation."""
        return self._name

    @property
    def extra_authorize_data(self) -> dict:
        """Extra data that needs to be appended to the authorize url."""
        return {
            "scope": "openapi",
            "redirect_uri": self.redirect_uri,
        }

class OAuth2FlowHandler(config_entry_oauth2_flow.AbstractOAuth2FlowHandler, domain=DOMAIN):
    """Config flow to handle U-Tec OAuth2 authentication."""

    DOMAIN = DOMAIN
    VERSION = 1

    @property
    def logger(self) -> logging.Logger:
        """Return logger."""
        return logging.getLogger(__name__)

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Handle a flow initialized by the user."""
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")

        if user_input is None:
            return self.async_show_form(
                step_id="user",
                data_schema=vol.Schema({
                    vol.Required(CONF_CLIENT_ID): str,
                    vol.Required(CONF_CLIENT_SECRET): str,
                })
            )

        return await self.async_step_pick_implementation(
            user_input={
                "implementation": self.DOMAIN,
                CONF_CLIENT_ID: user_input[CONF_CLIENT_ID],
                CONF_CLIENT_SECRET: user_input[CONF_CLIENT_SECRET],
            }
        )

    async def async_oauth_create_entry(self, data: dict) -> FlowResult:
        """Create an entry for the flow."""
        return self.async_create_entry(
            title="U-Tec Account",
            data=data,
        )

    async def async_step_reauth(self, user_input=None):
        """Perform reauth upon an API authentication error."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input=None):
        """Dialog that informs the user that reauth is required."""
        if user_input is None:
            return self.async_show_form(
                step_id="reauth_confirm",
                data_schema=vol.Schema({}),
            )

        return await self.async_step_user()