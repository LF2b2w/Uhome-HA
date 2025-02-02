"""Config flow for U-Tec integration."""
from typing import Any
import logging
import voluptuous as vol

from homeassistant.core import callback
from homeassistant.helpers import config_entry_oauth2_flow
from homeassistant.data_entry_flow import FlowResult
from homeassistant.const import CONF_CLIENT_ID, CONF_CLIENT_SECRET

from discovery import (
    api,
    auth,
)
from .const import (
    DOMAIN,
    AUTH_URL,
    TOKEN_URL,
)

class UTecOAuth2FlowHandler(
    config_entry_oauth2_flow.AbstractOAuth2FlowHandler, domain=DOMAIN
):
    """Config flow to handle U-Tec OAuth2 authentication."""

    DOMAIN = DOMAIN
    VERSION = 1

    @property
    def logger(self) -> logging.Logger:
        """Return logger."""
        return logging.getLogger(__name__)

    @property
    def extra_authorize_data(self) -> dict:
        """Extra data that needs to be appended to the authorize url."""
        return {
            "scope": "all",
            "response_type": "code",
        }

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle a flow start."""
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")

        if user_input is None:
            return self.async_show_form(
                step_id="user",
                data_schema=vol.Schema(
                    {
                        vol.Required(CONF_CLIENT_ID): str,
                        vol.Required(CONF_CLIENT_SECRET): str,
                    }
                ),
            )

        return await self.async_step_pick_implementation(
            user_input={
                "implementation": DOMAIN,
                CONF_CLIENT_ID: user_input[CONF_CLIENT_ID],
                CONF_CLIENT_SECRET: user_input[CONF_CLIENT_SECRET],
            }
        )

    async def async_oauth_create_entry(self, data: dict) -> FlowResult:
        """Create an entry for the flow."""
        try:
            # Initialize API and verify credentials
            session = config_entry_oauth2_flow.OAuth2Session(self.hass, self.flow_id, data)
            client = api.UTecAPIClient(session, self.hass)
            user_info = await client.get_user_info()

            # Use user info for the entry title
            name = f"{user_info.get('firstName', '')} {user_info.get('lastName', '')}".strip()
            if not name:
                name = "U-Tec Account"

            return self.async_create_entry(
                title=name,
                data=data,
            )
        except Exception as err:
            self.logger.error("Error creating entry: %s", err)
            return self.async_abort(reason="authorization_error")

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Get the options flow for this handler."""
        return UTecOptionsFlowHandler(config_entry)

class UTecOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle U-Tec options."""

    def __init__(self, config_entry):
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(self, user_input=None):
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        "scan_interval",
                        default=self.config_entry.options.get("scan_interval", 30),
                    ): int,
                }
            ),
        )

def oauth2_schema(impl: UTecOAuth2Implementation) -> vol.Schema:
    """Return oauth2 schema."""
    return vol.Schema(
        {
            vol.Required(CONF_CLIENT_ID): str,
            vol.Required(CONF_CLIENT_SECRET): str,
        }
    )

class UTecOAuth2Implementation(config_entry_oauth2_flow.LocalOAuth2Implementation):
    """U-Tec OAuth2 implementation."""

    def __init__(
        self,
        hass: HomeAssistant,
        domain: str,
        client_id: str,
        client_secret: str,
    ) -> None:
        """Initialize U-Tec OAuth2 implementation."""
        self._domain = domain
        super().__init__(
            hass=hass,
            domain=domain,
            client_id=client_id,
            client_secret=client_secret,
            authorize_url=AUTH_URL,
            token_url=TOKEN_URL,
        )

    @property
    def name(self) -> str:
        """Name of the implementation."""
        return "U-Tec"

    @property
    def domain(self) -> str:
        """Domain that is providing the implementation."""
        return self._domain

    async def async_generate_authorize_url(self, flow_id: str) -> str:
        """Generate authorization url."""
        url = await super().async_generate_authorize_url(flow_id)
        return f"{url}&scope=all"

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up U-Tec from a config entry."""
    implementation = UTecOAuth2Implementation(
        hass,
        DOMAIN,
        entry.data[CONF_CLIENT_ID],
        entry.data[CONF_CLIENT_SECRET],
    )

    config_entry_oauth2_flow.async_register_implementation(
        hass, implementation
    )

    return True