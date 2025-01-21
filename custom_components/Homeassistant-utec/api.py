"""API Client for U-tec Integration."""
from typing import Any, Dict, Optional
import aiohttp
import logging
from urllib.parse import urlencode

_LOGGER = logging.getLogger(__name__)

class UtecApiClient:
    """API Client for communicating with the U-tec OAuth2 service."""

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        token: Optional[Dict[str, Any]] = None,
        session: Optional[aiohttp.ClientSession] = None,
    ) -> None:
        """Initialize API client."""
        self._client_id = client_id
        self._client_secret = client_secret
        self._token = token
        self._session = session or aiohttp.ClientSession()

    async def async_get_access_token(self, code: str) -> Dict[str, Any]:
        """Get access token from authorization code."""
        from .const import OAUTH2_TOKEN

        params = {
            "grant_type": "authorization_code",
            "client_id": self._client_id,
            "code": code,
        }

        url = f"{OAUTH2_TOKEN}?{urlencode(params)}"

        async with self._session.post(url) as response:
            response.raise_for_status()
            return await response.json()

    async def async_refresh_token(self, refresh_token: str) -> Dict[str, Any]:
        """Refresh access token."""
        from .const import OAUTH2_TOKEN

        params = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": self._client_id,
            "client_secret": self._client_secret,
        }

        url = f"{OAUTH2_TOKEN}?{urlencode(params)}"

        async with self._session.post(url) as response:
            response.raise_for_status()
            return await response.json()

    async def close(self) -> None:
        """Close the session."""
        if self._session:
            await self._session.close()