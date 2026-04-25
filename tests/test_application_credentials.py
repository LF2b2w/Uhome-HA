"""Tests for application_credentials module."""

from custom_components.u_tec import application_credentials
from custom_components.u_tec.const import OAUTH2_AUTHORIZE, OAUTH2_TOKEN


async def test_async_get_authorization_server_returns_configured_urls(hass):
    server = await application_credentials.async_get_authorization_server(hass)
    assert server.authorize_url == OAUTH2_AUTHORIZE
    assert server.token_url == OAUTH2_TOKEN
