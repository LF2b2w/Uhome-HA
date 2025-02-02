# custom_components/utec/api.py
"""API client for U-Tec."""
import logging
from typing import Any, Dict, List, Optional
from datetime import datetime

from aiohttp import ClientSession
from homeassistant.helpers import config_entry_oauth2_flow
from const import API_BASE_URL

_LOGGER = logging.getLogger(__name__)

class APIClient(UhomeAPI):
    """Initialise API Client"""

    def __init__(
        self,
        session: config_entry_oauth2_flow.OAuth2Session,
        api_session: ClientSession,
    ) -> None:
        """Initialize the API client."""
        self._session = session
        self._api_session = api_session

    async def _async_request(
        self,
        namespace: str,
        name: str,
        payload: dict = None,
    ) -> dict:
        """Make an API request."""
        if payload is None:
            payload = {}

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self._session.token['access_token']}"
        }

        data = {
            "header": {
                "namespace": namespace,
                "name": name,
                "messageId": datetime.now().strftime("%Y%m%d%H%M%S"),
                "payloadVersion": "1"
            },
            "payload": payload
        }

        async with self._api_session.post(
            f"{API_BASE_URL}/action",
            headers=headers,
            json=data
        ) as response:
            response_data = await response.json()

            if "error" in response_data.get("payload", {}):
                error = response_data["payload"]["error"]
                raise UTecAPIError(
                    f"API request failed: {error.get('code')} - {error.get('message')}"
                )

            return response_data["payload"]

    async def get_devices(self) -> List[Dict[str, Any]]:
        """Get list of devices."""
        response = await self._async_request(
            namespace="Uhome.Device",
            name="Discovery"
        )
        return response.get("devices", [])

    async def get_device_state(self, device_id: str) -> Dict[str, Any]:
        """Get device state."""
        response = await self._async_request(
            namespace="Uhome.Device",
            name="Get",
            payload={"id": device_id}
        )
        return response.get("device", {})

    async def lock_device(self, device_id: str) -> None:
        """Lock a device."""
        await self._async_request(
            namespace="Uhome.Lock",
            name="Lock",
            payload={
                "device": {
                    "id": device_id
                }
            }
        )

    async def unlock_device(self, device_id: str) -> None:
        """Unlock a device."""
        await self._async_request(
            namespace="Uhome.Lock",
            name="Unlock",
            payload={
                "device": {
                    "id": device_id
                }
            }
        )

    async def get_user_info(self) -> Dict[str, Any]:
        """Get user information."""
        response = await self._async_request(
            namespace="Uhome.User",
            name="Get"
        )
        return response.get("user", {})

    async def set_notification_url(self, url: str) -> None:
        """Set notification URL for device events."""
        await self._async_request(
            namespace="Uhome.Notification",
            name="SetUrl",
            payload={"url": url}
        )

class UTecAPIError(Exception):
    """Exception for API errors."""