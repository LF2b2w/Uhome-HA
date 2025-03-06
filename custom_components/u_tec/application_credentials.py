"""Application credentials platform for the Uhome integration."""

from homeassistant.components.application_credentials import (
    AuthImplementation,
    AuthorizationServer,
)
from homeassistant.core import HomeAssistant

from .const import OAUTH2_AUTHORIZE, OAUTH2_TOKEN


async def async_get_authorization_server(hass: HomeAssistant) -> AuthorizationServer:
    """Return authorization server."""
    return AuthorizationServer(
        authorize_url=OAUTH2_AUTHORIZE,
        token_url=OAUTH2_TOKEN,
    )

async def async_get_implementations(
    hass: HomeAssistant,
) -> dict[str, AuthImplementation]:
    """Return a dict of AuthImplementation objects.

    This is required to avoid blocking imports.
    """
    return {}