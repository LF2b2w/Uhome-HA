"""The unwrapping OAuth implementations must be wired into both code paths.

Runtime token refresh resolves its implementation via the application_credentials
platform hook; the config flow builds its own in-memory implementation. Both must
use the U-Tec envelope-unwrapping classes, or refresh/auth silently break.
"""

from unittest.mock import AsyncMock, patch

from aioresponses import aioresponses

from custom_components.u_tec.const import DOMAIN, OAUTH2_TOKEN
from custom_components.u_tec.oauth import (
    UtecAuthImplementation,
    UtecLocalOAuth2Implementation,
)

_WRAPPED = {
    "code": 200,
    "data": {
        "access_token": "abc123",
        "token_type": "Bearer",
        "expires_in": 601200,
        "scope": "openapi",
    },
}


async def test_application_credentials_returns_unwrapping_implementation(hass):
    """Runtime path: the app-creds hook returns an unwrapping implementation."""
    from homeassistant.components.application_credentials import ClientCredential

    from custom_components.u_tec.application_credentials import (
        async_get_auth_implementation,
    )

    impl = await async_get_auth_implementation(
        hass, DOMAIN, ClientCredential("client-id", "client-secret")
    )
    assert isinstance(impl, UtecAuthImplementation)

    with aioresponses() as mock:
        mock.post(OAUTH2_TOKEN, payload=_WRAPPED)
        result = await impl._token_request(
            {"grant_type": "refresh_token", "refresh_token": "r"}
        )
    assert result["access_token"] == "abc123"
    assert result["expires_in"] == 601200


async def test_config_flow_uses_unwrapping_implementation(hass):
    """Config-flow path: replace-credentials sets an unwrapping flow_impl."""
    from custom_components.u_tec.config_flow import UhomeOAuth2FlowHandler

    handler = UhomeOAuth2FlowHandler()
    handler.hass = hass

    with patch.object(
        UhomeOAuth2FlowHandler,
        "async_step_auth",
        new=AsyncMock(return_value={"type": "external_step"}),
    ):
        await handler.async_step_replace_credentials(
            {"client_id": "client-id", "client_secret": "client-secret"}
        )

    assert isinstance(handler.flow_impl, UtecLocalOAuth2Implementation)
