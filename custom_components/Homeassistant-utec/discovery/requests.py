"""API Client for U-tec Integration."""
import uuid
import aiohttp
from typing import Any, Dict, Optional
import json
import logging
from requests.adapters import HTTPAdapter, Retry
from const import API_URL
import auth

_LOGGER = logging.getLogger(__name__)

class UhomeNamespace:
    """Uhome API namespaces."""
    USER = "Uhome.User"
    DEVICE = "Uhome.Device"
    CONFIGURE = "Uhome.Configure"

class UhomeName:
    """Uhome API actions."""
    SET = "SET"
    GET = "GET"
    DISCOVERY = "DISCOVERY"
    QUERY = "Query"
    COMMAND = "COMMAND"

class DeviceCapability:
    """Device capabilities supported by U-tec."""
    SWITCH = "st.switch"
    LOCK = "st.lock"
    LIGHT = "st.light"
    COLOR = "st.color"
    COLOR_TEMPERATURE = "st.colorTemperature"
    BATTERY = "st.BatteryLevel"
    # Add more capabilities as needed

class DeviceCommand:
    """Device commands supported by U-tec."""
    SET_LEVEL = "setLevel"
    SET_SWITCH = "setSwitch"
    SET_LOCK = "setLock"
    SET_COLOR = "setColor"
    SET_COLOR_TEMP = "setColorTemperature"
    # Add more commands as needed

class ReqAPI:
    """Class to send API calls."""

    def __init__(
        self,
        access_token: Optional[str] = None,
        session: Optional[aiohttp.ClientSession] = None,
    ) -> None:
        """Initialize API client."""
        self._access_token = access_token
        self._session = session or aiohttp.ClientSession()

    async def _api_request(
        self,
        namespace: str,
        name: str,
        payload: Dict[str, Any] = None,
    ) -> Dict[str, Any]:
        """Make an API request to U-tec."""
        if not self._access_token:
            if (res := await auth.async_refresh_token()) and res != "ok":
                return self._logger.debug(f"Refresh Token failed due to: {res}")

        # Prepare the base request data
        request_data = {
            "header": {
                "namespace": namespace,
                "name": name,
                "messageId": str(uuid.uuid4()),
                "payloadVersion": "1"
            },
            "payload": payload or {}
        }

        # Add authentication in payload if not using header
        #request_data["authentication"] = {
        #        "type": "Bearer",
        #        "token": self._access_token
        #    }

        # Prepare headers
        headers = {
            "Content-Type": "application/json"
        }

        # Add auth header if specified
        headers["Authorization"] = f"Bearer {self._access_token}"

        try:
            async with self._session.post(
                API_URL,
                json=request_data,
                headers=headers
            ) as response:
                response.raise_for_status()
                return await response.json()

        except aiohttp.ClientError as err:
            _LOGGER.error("API request failed: %s", err)
            raise

    async def discover_devices(self) -> Dict[str, Any]:
        """Discover all devices."""
        return await self._api_request(
            namespace=UhomeNamespace.DEVICE,
            action=UhomeName.DISCOVERY
        )

    async def get_device_status(self, device_id: str) -> Dict[str, Any]:
        """Get status of a specific device."""
        return await self._api_request(
            namespace=UhomeNamespace.DEVICE,
            action=UhomeName.QUERY,
            payload={"deviceId": device_id}
        )

    async def get_user_info(self) -> Dict[str, Any]:
        """Get user information."""
        return await self._api_request(
            namespace=UhomeNamespace.USER,
            action=UhomeName.GET
        )

    async def set_configuration(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Set system configuration."""
        return await self._api_request(
            namespace=UhomeNamespace.CONFIGURE,
            action=UhomeName.SET,
            payload=config
        )

    async def send_device_command(
        self,
        device_id: str,
        capability: str,
        command_name: str,
        arguments: Dict[str, Any],
        custom_data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Send a command to a device."""
        payload = {
            "devices": [
                {
                    "id": device_id,
                    "customData": custom_data,
                    "command": {
                        "capability": capability,
                        "name": command_name,
                        "arguments": arguments
                    }
                }
            ]
        }

        return await self._api_request(
            namespace="Uhome.Device",
            action="Command",
            payload=payload
        )

    async def close(self) -> None:
        """Close the session."""
        if self._session:
            await self._session.close()

    @property
    def token(self) -> Optional[str]:
        """Get current access token."""
        return self._access_token