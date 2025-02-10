"""Support for Uhome Battery Sensors."""

from utec_py.devices.lock import Lock as UhomeLock

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
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
    """Set up Uhome battery sensors based on a config entry."""
    coordinator: UhomeDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]

    # Add battery sensors for locks that have them
    async_add_entities(
        UhomeBatterySensorEntity(coordinator, device_id)
        for device_id, device in coordinator.devices.items()
        if isinstance(device, UhomeLock)
    )


class UhomeBatterySensorEntity(CoordinatorEntity, SensorEntity):
    """Representation of a Uhome battery sensor."""

    _attr_device_class = SensorDeviceClass.BATTERY

    def __init__(self, coordinator: UhomeDataUpdateCoordinator, device_id: str) -> None:
        """Initialize the battery sensor."""
        super().__init__(coordinator)
        self._device = coordinator.devices[device_id]
        self._attr_unique_id = f"{DOMAIN}_battery_{device_id}"
        self._attr_name = f"{self._device.name} Battery"
        self._attr_device_info = self._device.device_info

    @property
    def battery_level(self) -> int | None:
        """Return battery level."""
        return self.battery_level
