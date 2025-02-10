"""Data coordinator for Uhome integration."""

from datetime import timedelta
import logging

from utec_py.api import UHomeApi
from utec_py.devices.device import BaseDevice
from utec_py.devices.light import Light
from utec_py.devices.lock import Lock
from utec_py.devices.switch import Switch
from utec_py.exceptions import ApiError, AuthenticationError
from voluptuous import Any

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

_LOGGER = logging.getLogger(__name__)


class UhomeDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching Uhome data."""

    def __init__(
        self, hass: HomeAssistant, api: UHomeApi
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name="Uhome devices",
            update_interval=timedelta(seconds=30),
        )
        self.api = api
        self.devices: dict[str, BaseDevice] = {}

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from API endpoint."""
        try:
            # Validate authentication first
            #if not await self.api.validate_auth():
            #    raise ConfigEntryAuthFailed("Invalid authentication")

            # Discover devices
            discovery_data = await self.api.discover_devices()
            devices_data = discovery_data.get("payload", {}).get("devices", [])

            # Update existing devices and add new ones
            for device_data in devices_data:
                device_id = device_data["id"]
                handle_type = device_data["handleType"]

                if device_id not in self.devices:
                    # Create new device instance based on handle type
                    if "lock" in handle_type.lower():
                        device = Lock(device_data, self.api)
                    elif "light" in handle_type.lower():
                        device = Light(device_data, self.api)
                    elif "switch" in handle_type.lower():
                        device = Switch(device_data, self.api)
                    else:
                        continue

                    self.devices[device_id] = device

                # Update device state
                await self.devices[device_id].update()

            return {
                device_id: device.get_state_data()
                for device_id, device in self.devices.items()
            }

        except AuthenticationError as err:
            raise ConfigEntryAuthFailed from err
        except ApiError as err:
            raise UpdateFailed(f"Error communicating with API: {err}") from err
