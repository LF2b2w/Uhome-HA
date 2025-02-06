"""API wrapper for Uhome/Utec API."""

from venv import logger

from aiohttp import ClientResponse, ClientSession
from utec_py_LF2b2w.api import UHomeApi
from utec_py_LF2b2w.auth import AbstractAuth

from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_entry_oauth2_flow


class AsyncConfigEntryAuth(AbstractAuth):
    """Provide Uhome-HA authentication tied to an OAuth2 based config entry."""

    def __init__(
        self,
        websession: ClientSession,
        oauth_session: config_entry_oauth2_flow.OAuth2Session,
    ) -> None:
        """Initialize Uhome-HA auth."""
        super().__init__(websession)
        self._oauth_session = oauth_session

    async def async_get_access_token(self) -> str:
        """Return a valid access token."""
        await self._oauth_session.async_ensure_token_valid()
        return self._oauth_session.token["access_token"]

    async def make_request(self, method: str, url: str, **kwargs) -> ClientResponse:
        """Make an authenticated API request."""
        access_token = await self.async_get_access_token()
        headers = kwargs.get("headers", {})
        headers["Authorization"] = f"Bearer {access_token}"
        kwargs["headers"] = headers

        return await self.websession.request(method, f"{self.host}/{url}", **kwargs)


class UhomeApiWrapper:
    """Wrapper for the U‑tec API that uses Home Assistant’s OAuth2 session."""

    def __init__(self, hass: HomeAssistant, oauth_session) -> None:
        """Initialize the API wrapper.

        :param hass: Home Assistant instance.
        :param oauth_session: Home Assistant-managed OAuth2 session.
        """
        self.hass = hass
        self.session = oauth_session
        # Create the UHomeApi instance using the provided session.
        # Assume UHomeApi accepts a session that already appends the required
        # Authorization headers based on tokens managed by Home Assistant.
        self.api = UHomeApi(self.session)

    async def discover_devices(self) -> dict:
        """Discover available devices via the API."""
        try:
            return await self.api.discover_devices()
        except (ConnectionError, TimeoutError) as err:
            logger.error("Network error discovering devices: %s", err)
            return {}
        except ValueError as err:
            logger.error("Value error discovering devices: %s", err)
            return {}

    async def send_command(
        self,
        device_id: str,
        capability: str,
        command: str,
        arguments: dict | None = None,
    ) -> dict:
        """Send a command to a specific device."""
        try:
            return await self.api.send_command(
                device_id, capability, command, arguments
            )
        except (ConnectionError, TimeoutError, ValueError) as err:
            logger.error("Error sending command: %s", err)
            return {}

    async def async_close(self):
        """Close any resources if needed."""
        # Home Assistant’s OAuth2 session handles token refresh internally.
