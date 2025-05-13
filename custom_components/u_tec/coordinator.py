"""Data coordinator for Uhome integration."""

from datetime import timedelta
import logging

from custom_components.u_tec.const import SIGNAL_DEVICE_UPDATE, SIGNAL_NEW_DEVICE

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.dispatcher import async_dispatcher_send
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
        self.added_sensor_entities = set()
        self.push_devices = []
        self.blacklisted_devices = []
        _LOGGER.info("Uhome data coordinator initialized")

    async def _async_update_data(self) -> dict[str, dict]:
        """Fetch data from API endpoint."""
        _LOGGER.debug("Updating Uhome device data")
        try:
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
                        async_dispatcher_send(self.hass, SIGNAL_NEW_DEVICE)
                    except DeviceError as err:
                        _LOGGER.error(
                            "Error updating new device %s: %s", device_id, err
                        )
                else:
                    _LOGGER.debug("Updating existing device: %s", device_id)
                    # Update device state
                    try:
                        await self.devices[device_id].update()
                        _LOGGER.debug(
                            "Successfully updated data for %s devices",
                            len(self.devices),
                        )
                    except DeviceError as err:
                        _LOGGER.error("Error updating device %s: %s", device_id, err)

            return {
                device_id: device.get_state_data()
                for device_id, device in self.devices.items()
            }
        except AuthenticationError as err:
            raise ConfigEntryAuthFailed from err
        except ApiError as err:
            raise UpdateFailed(f"Error communicating with API: {err}") from err
        except ValueError as err:
            raise UpdateFailed(f"Unexpected error updating data: {err}") from err

    async def update_push_data(self, push_data):
        """Process push update from webhook."""

        _LOGGER.debug("Processing push update: %s", push_data)

        try:
            # Check if the data has the expected structure
            if (
                "payload" in push_data
                and "devices" in push_data["payload"]
                and isinstance(push_data["payload"]["devices"], list)
            ):
                devices_data = push_data["payload"]["devices"]

                for device_data in devices_data:
                    device_id = device_data.get("id")

                    if not device_id:
                        _LOGGER.warning("Device ID missing in push update")
                        continue

                    # Check if this device should receive push updates
                    if self.push_devices and device_id not in self.push_devices:
                        _LOGGER.debug(
                            "Skipping push update for device %s (not in selected devices)",
                            device_id,
                        )
                        continue

                    if device_id in self.devices:
                        # Get the device instance
                        device = self.devices[device_id]

                        # Update the device's state data directly
                        # The format matches what the device expects
                        await device.update_state_data(device_data)

                        _LOGGER.debug(
                            "Updated device %s with push data: %s",
                            device_id,
                            device_data,
                        )

                        # Notify listeners that the device has been updated
                        _LOGGER.debug("Dispatching update for device: %s", device_id)
                        async_dispatcher_send(
                            self.hass,
                            f"{SIGNAL_DEVICE_UPDATE}_{device_id}",
                            device.get_state_data(),
                        )
                    else:
                        _LOGGER.debug(
                            "Received update for unknown device: %s", device_id
                        )

                # Trigger data update for all entities
                self.async_set_updated_data(self.data)

            else:
                _LOGGER.warning("Unexpected push data format: %s", push_data)

        except (ValueError, TypeError, AttributeError) as err:
            _LOGGER.error("Error processing push update: %s", err)
