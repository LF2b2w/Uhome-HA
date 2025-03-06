"""Application credentials platform for the Uhome integration."""

from typing import Any, cast

from homeassistant.components.application_credentials import (
    AuthImplementation,
    AuthorizationServer,
    ClientCredential,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_entry_oauth2_flow
import voluptuous as vol

from .const import DOMAIN, OAUTH2_AUTHORIZE, OAUTH2_TOKEN, DEFAULT_API_SCOPE


async def async_get_authorization_server(hass: HomeAssistant) -> AuthorizationServer:
    """Return authorization server."""
    return AuthorizationServer(
        authorize_url=OAUTH2_AUTHORIZE,
        token_url=OAUTH2_TOKEN,
    )


async def async_get_implementations(
    hass: HomeAssistant,
) -> dict[str, AuthImplementation]:
    """Return a dict of AuthImplementation objects."""
    return {
        DOMAIN: UhomeAuthImplementation(hass),
    }


class UhomeAuthImplementation(AuthImplementation):
    """Uhome API Auth Implementation."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize Uhome auth implementation."""
        self.hass = hass
        self._api_scope = DEFAULT_API_SCOPE

    @property
    def name(self) -> str:
        """Return name of the implementation."""
        return "U-Tec"

    @property
    def domain(self) -> str:
        """Return the domain used by the implementation."""
        return DOMAIN

    @property
    def extra_authorize_data(self) -> dict[str, vol.Any]:
        """Extra data that needs to be appended to the authorize url."""
        return {"scope": self._api_scope or DEFAULT_API_SCOPE}

    async def async_get_client_credential(self) -> ClientCredential | None:
        """Return the client credential."""
        # This implementation doesn't have predefined client credentials
        # The config flow will prompt the user for them
        return None

    async def async_resolve_external_data(self, external_data: dict) -> dict:
        """Resolve the authorization code to tokens."""
        # Get the flow
        flow = await config_entry_oauth2_flow.async_get_flow(
            self.hass, external_data["flow_id"]
        )

        # Get client credentials from the flow
        client_id = flow.data.get("client_id")
        client_secret = flow.data.get("client_secret")
        self._api_scope = flow.data.get("api_scope", DEFAULT_API_SCOPE)

        # Create the implementation
        implementation = config_entry_oauth2_flow.LocalOAuth2Implementation(
            self.hass,
            DOMAIN,
            client_id,
            client_secret,
            OAUTH2_AUTHORIZE,
            OAUTH2_TOKEN,
        )

        # Register the implementation
        config_entry_oauth2_flow.register_oauth2_implementation(
            self.hass, DOMAIN, implementation
        )

        # Resolve the external data
        return await implementation.async_resolve_external_data(external_data)

    async def async_generate_authorize_url(self, flow_id: str) -> str:
        """Generate authorization url to redirect the user to."""
        # Get the flow
        flow = await config_entry_oauth2_flow.async_get_flow(self.hass, flow_id)

        # Get client credentials from the flow
        client_id = flow.data.get("client_id")
        client_secret = flow.data.get("client_secret")
        self._api_scope = flow.data.get("api_scope", DEFAULT_API_SCOPE)

        # Create the implementation
        implementation = config_entry_oauth2_flow.LocalOAuth2Implementation(
            self.hass,
            DOMAIN,
            client_id,
            client_secret,
            OAUTH2_AUTHORIZE,
            OAUTH2_TOKEN,
        )

        # Register the implementation
        config_entry_oauth2_flow.register_oauth2_implementation(
            self.hass, DOMAIN, implementation
        )

        # Generate the authorize URL
        return await implementation.async_generate_authorize_url(flow)