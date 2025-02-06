"""UHome device coordinator."""

from datetime import timedelta
import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import (
    ConfigEntryNotReady,
    DataUpdateCoordinator,
    UpdateFailed,
)

from .api import UhomeApiWrapper
from .entity import UtecEntity

logger = logging.getLogger(__name__)


class UHomeDeviceCoordinator(DataUpdateCoordinator):
    """Class to manage fetching UHome device data from the API."""

    def __init__(
        self,
        hass: HomeAssistant,
        api: UhomeApiWrapper,
        device_id: str,
    ) -> None:
        """Initialize the coordinator."""
        self.api = api
        self.device_id = device_id
        self._devices: dict[str, UtecEntity] = {}

        super().__init__(
            hass,
            logger,
            name=f"uhome_{device_id}_coordinator",
            update_interval=timedelta(seconds=30),
        )

    async def async_config_entry_first_refresh(self) -> None:
        """First refresh of data to ensure devices are available."""

        def raise_error(message):
            raise ConfigEntryNotReady(message)

        try:
            # Initial device discovery
            try:
                discovery_data = await self.api.discover_devices()
                if not discovery_data:
                    raise_error("No devices found during initial setup")

                devices_data = discovery_data.get("payload", {}).get("devices", [])
                if not devices_data:
                    logger.warning("No devices found in discovery data")
                    return

                # Initialize devices
                for device_data in devices_data:
                    device_id = device_data.get("id")
                    if not device_id:
                        continue

                    self._devices[device_id] = device_data
                    await self.async_update_data()
                    logger.dev(
                        f"Initialized device {device_id}",
                        extra={"device_id": device_id},
                    )

                if not self._devices:
                    raise_error("No devices could be initialised")

                self.data = {
                    device_id: self._get_device_state(device)
                    for device_id, device in self.devices.items()
                }

                logger.info("Initialized %s devices", len(self.data))

            except (ConnectionError, TimeoutError, ValueError) as err:
                raise_error(f"Failed to discover devices: {err}")
        except ConfigEntryNotReady as err:
            logger.error("Failed to setup devices: %s", err)

    async def _async_update_data(self) -> Any:
        """Fetch data from UHome API."""
        try:
            return await self.api.async_get_device_state(self.device_id)
        except Exception as err:
            raise UpdateFailed(f"Error fetching data: {err}") from err

    async def get_device(self, device_id: str):
        """Get a device by its ID."""
        return await self.data.get_device(device_id, {})

    async def async_update_device(self, device_id: str):
        """Update device in Home Assistant."""
        state = await self._async_get_device_state(device_id)
        if state:
            self.hass.states.async_set(
                f"uhome.{device_id}",
                state["state"],
                attributes=state["attributes"],
            )

    def _get_device_state(self, device: UtecEntity) -> dict[str, Any]:
        """Return the state of a device."""
        return {
            "available": True,
            "state": device.state_attributes,
        }

    @property
    def available(self) -> bool:
        """Return if coordinator is available."""
        return self._available

    @property
    def devices(self) -> dict[str, UtecEntity]:
        """Return the devices."""
        return self._devices

    @property
    def device_ids(self) -> list[str]:
        """Return the device IDs."""
        return list(self.devices.keys())
