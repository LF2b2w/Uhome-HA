"""Tests for U-Tec OAuth token-envelope unwrapping.

U-Tec's /token endpoint wraps the token under {"code","data":{...}} instead of
returning the RFC-6749 fields at the top level. Home Assistant's stock OAuth2
implementation looks for access_token/expires_in at the top level, so without
unwrapping a token refresh silently yields no usable token and the access token
goes stale. These cover the unwrap and its wiring into the implementations.
"""

from unittest.mock import AsyncMock, patch

import pytest

from homeassistant.helpers import config_entry_oauth2_flow

from custom_components.u_tec.const import DOMAIN, OAUTH2_AUTHORIZE, OAUTH2_TOKEN
from custom_components.u_tec.oauth import (
    UtecLocalOAuth2Implementation,
    _unwrap_utec_token,
)

_WRAPPED = {
    "code": 200,
    "data": {
        "access_token": "abc123",
        "token_type": "Bearer",
        "expires_in": 601200,
        "scope": "openapi",
        "refresh_token": "r-456",
    },
}


def test_unwrap_lifts_nested_data_to_top_level():
    assert _unwrap_utec_token(_WRAPPED) == _WRAPPED["data"]


def test_unwrap_passthrough_standard_response():
    standard = {"access_token": "xyz", "token_type": "Bearer", "expires_in": 3600}
    assert _unwrap_utec_token(standard) == standard


def test_unwrap_raises_when_no_access_token_present():
    with pytest.raises(ValueError):
        _unwrap_utec_token({"code": 401, "data": {"message": "bad refresh token"}})


async def test_local_impl_token_request_unwraps(hass):
    """The mixin unwraps whatever the underlying HA token request returns.

    We patch the superclass ``_token_request`` (HA's HTTP boundary) rather than
    mock the network: hitting it for real spins up an aiohttp clientsession whose
    pycares DNS resolver leaves a daemon ``_run_safe_shutdown_loop`` thread that
    older pytest-homeassistant-custom-component builds flag as a lingering-thread
    failure. Patching the boundary keeps the test hermetic and version-agnostic
    while still proving the mixin is wired in and unwraps the {code,data} envelope.
    """
    impl = UtecLocalOAuth2Implementation(
        hass, DOMAIN, "client-id", "client-secret", OAUTH2_AUTHORIZE, OAUTH2_TOKEN,
    )
    with patch.object(
        config_entry_oauth2_flow.LocalOAuth2Implementation,
        "_token_request",
        new=AsyncMock(return_value=_WRAPPED),
    ):
        result = await impl._token_request(
            {"grant_type": "refresh_token", "refresh_token": "r"}
        )
    assert result["access_token"] == "abc123"
    assert result["expires_in"] == 601200
    assert result["refresh_token"] == "r-456"
