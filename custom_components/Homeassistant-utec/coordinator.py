import asyncio
from datetime import timedelta
import logging
from typing import Dict, List, Optional, Any
import async_timeout

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
    UpdateFailed,
)
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady

from .api import UtecAPI
from device_factory import DeviceFacilitator
from device_types import BaseDevice
from exceptions import DeviceError, AuthError

_LOGGER = logging.getLogger(__name__)

class UtecDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching UHome data."""

    def __init__(
        self,
        hass: HomeAssistant,
        api: UtecAPI,
        update_interval: timedelta = timedelta(seconds=30),
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name="Utec Devices",
            update_interval=update_interval,
        )
        self.api = api
        self.devices: Dict[str, BaseDevice] = {}
        self._available = True

    async def async_config_entry_first_refresh(self) -> None:
        """First refresh of data to ensure devices are available."""
        try:
            # Initial device discovery
                try:
                    discovery_data = await self.api.discover_devices()
                    if not discovery_data:
                        raise ConfigEntryNotReady(
                            "No devices found during initial setup"
                        )

                    devices_data = discovery_data.get("payload", {}).get("devices", [])
                    if not devices_data:
                        _LOGGER.warning("No devices found in discovery data")
                        return

                    # Initialize devices
                    for device_data in devices_data:
                        device_id = device_data.get("id")
                        if not device_id:
                            continue

                        try:
                            device = self._device_facilitator.create_device(
                                device_data, self.api
                            )
                            if device:
                                self._devices[device_id] = device
                                # Initial state fetch for the device
                                await device.update()
                                _LOGGER.debug(
                                    "Successfully initialized device %s (%s)",
                                    device.name,
                                    device_id
                                )
                        except Exception as err:
                            _LOGGER.warning(
                                "Failed to initialize device %s: %s",
                                device_id,
                                err
                            )

                    if not self._devices:
                        raise ConfigEntryNotReady(
                            "No devices could be initialized"
                        )

                    # Store initial state
                    self.data = {
                        device_id: self._get_device_state(device)
                        for device_id, device in self._devices.items()
                    }

                    _LOGGER.info(
                        "Successfully initialized %d devices",
                        len(self._devices)
                    )

                except Exception as err:
                    _LOGGER.error("Failed to discover devices: %s", err)
                    raise ConfigEntryNotReady(
                        f"Failed to discover devices: {err}"
                    ) from err

        except asyncio.TimeoutError as err:
            _LOGGER.error("Timeout during initial refresh")
            raise ConfigEntryNotReady(
                "Timeout during initial device setup"
            ) from err
        except Exception as err:
            _LOGGER.error("Unexpected error during initial refresh: %s", err)
            raise ConfigEntryNotReady(
                f"Unexpected error during setup: {err}"
            ) from err
    
    async def _async_update_data(self) -> Dict[str, Any]:
        """Fetch data from API endpoint."""
        try:
            async with async_timeout.timeout(30):
                # Discover devices if we don't have any
                if not self.devices:
                    await self._discover_devices()

                # Update all device states
                device_states = {}
                for device_id, device in self.devices.items():
                    try:
                        await device.update()
                        device_states[device_id] = {
                            "available": True,
                            "state": device.state_attributes,
                        }
                    except Exception as err:
                        _LOGGER.error(f"Error updating device {device_id}: {err}")
                        device_states[device_id] = {
                            "available": False,
                            "state": {},
                        }

                self._available = True
                return device_states

        except AuthError as err:
            self._available = False
            raise ConfigEntryAuthFailed from err
        except Exception as err:
            self._available = False
            raise UpdateFailed(f"Error communicating with API: {err}")

    async def _discover_devices(self) -> None:
        """Discover devices from the API."""
        try:
            discovery_response = await self.api.discover_devices()
            devices_data = discovery_response["payload"]["devices"]

            for device_data in devices_data:
                try:
                    device_id = device_data["id"]
                    device = Device_factory.create_device(device_data, self.api)
                    self.devices[device_id] = device
                except DeviceError as err:
                    _LOGGER.error(f"Error creating device: {err}")

        except Exception as err:
            _LOGGER.error(f"Error discovering devices: {err}")
            raise UpdateFailed(f"Device discovery failed: {err}")

    @property
    def available(self) -> bool:
        """Return if coordinator is available."""
        return self._available

    def get_device(self, device_id: str) -> Optional[BaseDevice]:
        """Get a device by ID."""
        return self.devices.get(device_id)

class UtecEntity(CoordinatorEntity):
    """Base entity for Utec devices."""

    def __init__(
        self,
        coordinator: UtecDataUpdateCoordinator,
        device_id: str,
    ) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        self._device_id = device_id
        self._device = coordinator.get_device(device_id)

        if self._device is None:
            raise ValueError(f"Device {device_id} not found in coordinator")

    @property
    def device_info(self) -> Dict[str, Any]:
        """Return device information for the entity."""
        device_info = self._device._discovery_data.get("deviceInfo", {})
        return {
            "identifiers": {("Utec", self._device_id)},
            "name": self._device._name,
            "manufacturer": device_info.get("manufacturer", "U-tec"),
            "model": device_info.get("model", "Unknown"),
            "hw_version": device_info.get("hwVersion"),
        }

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        device_state = self.coordinator.data.get(self._device_id, {})
        return self.coordinator.available and device_state.get("available", False)

    @property
    def unique_id(self) -> str:
        """Return a unique ID."""
        return f"Utec_{self._device_id}"

    @property
    def name(self) -> str:
        """Return the name of the entity."""
        return self._device._name