"""Base class for Utec entities."""

from typing import Any

from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import UHomeDeviceCoordinator


class UtecEntity(CoordinatorEntity):
    """Base HA entity for Utec devices."""

    def __init__(
        self,
        coordinator: UHomeDeviceCoordinator,
        device_id: str,
    ) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        self._device_id = device_id
        self._device = coordinator.get_device(device_id)

        if self._device is None:
            raise ValueError(f"Device {device_id} not found in coordinator")

    @property
    def device_info(self) -> dict[str, Any]:
        """Return device information for the entity."""
        device_info = self._device.get_discovery_data().get("deviceInfo", {})
        return {
            "identifiers": {("Utec", self._device_id)},
            "name": self._device.name,
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
        return self._device.name
