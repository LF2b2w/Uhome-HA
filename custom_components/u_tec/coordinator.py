"""Data coordinator for Uhome integration."""

from datetime import timedelta
import logging

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from utec_py.api import UHomeApi
from utec_py.devices.device import BaseDevice
from utec_py.devices.light import Light
from utec_py.devices.lock import Lock
from utec_py.devices.switch import Switch
from utec_py.exceptions import ApiError, AuthenticationError, DeviceError

_LOGGER = logging.getLogger(__name__)


class UhomeDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching Uhome data."""

    def __init__(self, hass: HomeAssistant, api: UHomeApi) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name="Uhome devices",
            update_interval=timedelta(seconds=30),
        )
        self.api = api
        self.devices: dict[str, BaseDevice] = {}
        _LOGGER.info("Uhome data coordinator initialized")

    async def _async_update_data(self) -> None:
        """Fetch data from API endpoint."""
        _LOGGER.debug("Updating Uhome device data")
        try:
            # Validate authentication first
            # if not await self.api.validate_auth():
            #    raise ConfigEntryAuthFailed("Invalid authentication")

            # Discover devices
            _LOGGER.debug("Discovering Uhome devices")
            discovery_data = await self.api.discover_devices()
            if not discovery_data or "payload" not in discovery_data:
                _LOGGER.error("Invalid discovery data received: %s", discovery_data)
                return {}
            devices_data = discovery_data.get("payload", {}).get("devices", [])
            _LOGGER.debug("Found %s devices in discovery data", len(devices_data))

            # Update existing devices and add new ones
            for device_data in devices_data:
                device_id = device_data["id"]
                if not device_id:
                    continue
                handle_type = device_data["handleType"]

                if device_id not in self.devices:
                    # Create new device instance based on handle type
                    if "lock" in handle_type.lower():
                        _LOGGER.info("Adding new lock device: %s", device_id)
                        device = Lock(device_data, self.api)
                    elif "light" in handle_type.lower():
                        _LOGGER.info("Adding new light device: %s", device_id)
                        device = Light(device_data, self.api)
                    elif "switch" in handle_type.lower():
                        _LOGGER.info("Adding new switch device: %s", device_id)
                        device = Switch(device_data, self.api)
                    elif "dimmer" in handle_type.lower():
                        _LOGGER.info("Adding new light device: %s", device_id)
                        device = Light(device_data, self.api)
                    else:
                        _LOGGER.debug(
                            "Skipping device %s with unsupported handle type: %s",
                            device_id,
                            handle_type,
                        )
                        continue

                    self.devices[device_id] = device
                    try:
                        await device.update()  # Immediately get state data
                    except DeviceError as err:
                        _LOGGER.error("Error updating new device %s: %s", device_id, err)
                else:
                    _LOGGER.debug("Updating existing device: %s", device_id)
                    # Update device state
                    try:
                        await self.devices[device_id].update()
                        _LOGGER.debug("Successfully updated data for %s devices", len(self.devices))
                    except DeviceError as err:
                        _LOGGER.error("Error updating device %s: %s", device_id, err)
                    
                
            return {
                device_id: device.get_state_data()
                for device_id, device in self.devices.items()
            }

        except AuthenticationError as err:
            raise ConfigEntryAuthFailed from err
        except ApiError as err:
            raise UpdateFailed("Error communicating with API: {err}") from err
        except ValueError as err:
            raise UpdateFailed("Unexpected error updating data: %s", err)
