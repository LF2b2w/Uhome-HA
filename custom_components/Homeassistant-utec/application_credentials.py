from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_entry_oauth2_flow
from homeassistant.components.application_credentials import (
    AuthImplementation,
    AuthorizationServer,
    ClientCredential
)
from aiohttp import ClientSession
import datetime
from typing import Any, Dict, Optional
import logging

from .const import OAUTH2_AUTHORIZE,OAUTH2_TOKEN,DOMAIN

class UtecOAuth2Implementation(AuthImplementation):
    """Utec OAuth2 implementation for Home Assistant."""

    def __init__(
        self,
        hass: HomeAssistant,
        domain: str,
        client: ClientCredential,
        authorization_server: AuthorizationServer,
    ) -> None:
        """Initialize Utec OAuth2 implementation."""
        super().__init__(hass, domain, client, authorization_server)
        self.session = ClientSession()
        self._access_token: Optional[str] = None
        self._refresh_token: Optional[str] = None
        self._expires_at: Optional[datetime.datetime] = None

    @property
    def is_token_expired(self) -> bool:
        """Check if the token is expired."""
        return (
            datetime.datetime.now(datetime.timezone.utc) > self._expires_at
            if self._expires_at
            else True
        )

    async def async_generate_authorize_url(self, flow_id: str) -> str:
        """Generate authorization URL for OAuth2 flow."""
        return (
            f"{self.auth_server.authorize_url}"
            f"?response_type=code"
            f"&client_id={self.client_id}"
            f"&redirect_uri={self.redirect_uri}"
            f"&state={flow_id}"
        )

    async def async_resolve_external_data(self, external_data: dict) -> dict:
        """Resolve the authorization code to tokens."""
        code = external_data.get("code")
        if not code:
            raise config_entry_oauth2_flow.OAuth2AuthError("Missing authorization code")

        return await self._token_request({
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": self.redirect_uri,
        })

    async def async_refresh_token(self, token: Dict[str, Any]) -> dict:
        """Refresh tokens."""
        return await self._token_request({
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "grant_type": "refresh_token",
            "refresh_token": token["refresh_token"],
        })

    async def _token_request(self, data: dict) -> dict:
        """Make token request."""
        async with self.session.post(
            self.auth_server.token_url,
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        ) as resp:
            if resp.status != 200:
                raise config_entry_oauth2_flow.OAuth2AuthError(
                    f"Token request failed: {await resp.text()}"
                )

            token_data = await resp.json()
            self._update_token(token_data)
            return token_data

    def _update_token(self, token: dict) -> None:
        """Update token information."""
        self._access_token = token["access_token"]
        self._refresh_token = token.get("refresh_token")
        expires_in = token["expires_in"]
        self._expires_at = (
            datetime.datetime.now(datetime.timezone.utc) +
            datetime.timedelta(seconds=expires_in - 30)
        )

async def async_get_auth_implementation(
    hass: HomeAssistant,
    auth_domain: str,
    credential: ClientCredential,
) -> UtecOAuth2Implementation:
    """Return Utec auth implementation."""
    return UtecOAuth2Implementation(
        hass,
        auth_domain,
        credential,
        AuthorizationServer(
            authorize_url=OAUTH2_AUTHORIZE,
            token_url=OAUTH2_TOKEN,
        ),
    )