"""Application credentials platform for the Uhome integration."""

from homeassistant.components.application_credentials import (
    AuthorizationServer,
    ClientCredential,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_entry_oauth2_flow

from .const import OAUTH2_AUTHORIZE, OAUTH2_TOKEN
from .oauth import UtecAuthImplementation


async def async_get_authorization_server(hass: HomeAssistant) -> AuthorizationServer:
    """Return authorization server."""
    return AuthorizationServer(
        authorize_url=OAUTH2_AUTHORIZE,
        token_url=OAUTH2_TOKEN,
    )


async def async_get_auth_implementation(
    hass: HomeAssistant, auth_domain: str, credential: ClientCredential
) -> config_entry_oauth2_flow.AbstractOAuth2Implementation:
    """Return a custom auth implementation that unwraps U-Tec's token envelope.

    Defining this hook overrides application_credentials' default
    AuthImplementation for the runtime (refresh) path, so token refresh can
    parse U-Tec's non-standard ``{code,data}`` response. See ``oauth.py``.
    """
    return UtecAuthImplementation(
        hass,
        auth_domain,
        credential,
        await async_get_authorization_server(hass),
    )
