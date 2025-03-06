"""Support for Uhome Door Sensors."""

from utec_py.devices.lock import UhomeLock

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import UhomeDataUpdateCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Uhome door sensors based on a config entry."""
    coordinator: UhomeDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]

    # Add door sensors for locks that have them
    async_add_entities(
        UhomeDoorSensor(coordinator, device_id)
        for device_id, device in coordinator.devices.items()
        if isinstance(device, UhomeLock) and device.has_door_sensor
    )


class UhomeDoorSensor(CoordinatorEntity, BinarySensorEntity):
    """Representation of a Uhome door sensor."""

    _attr_device_class = BinarySensorDeviceClass.DOOR

    def __init__(self, coordinator: UhomeDataUpdateCoordinator, device_id: str) -> None:
        """Initialize the door sensor."""
        super().__init__(coordinator)
        self._device = coordinator.devices[device_id]
        self._attr_unique_id = f"{DOMAIN}_door_{device_id}"
        self._attr_name = f"{self._device.name} Door"
        self._attr_device_info = self._device.device_info

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self.coordinator.last_update_success and self._device.available

    @property
    def is_on(self) -> bool | None:
        """Return true if the door is open."""
        return (
            not self._device.is_door_closed
            if self._device.is_door_closed is not None
            else None
        )
