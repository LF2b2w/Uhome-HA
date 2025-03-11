"""Support for Uhome Battery Sensors."""

from utec_py.devices.lock import Lock as UhomeLock

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.const import PERCENTAGE
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
    coordinator: UhomeDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]

    # Add battery sensors for locks that have them
    entities = []
    UhomeBatterySensorEntity(coordinator, device_id)
    for device_id, device in coordinator.devices.items():
        if hasattr(device, 'has_capability') and device.has_capability("st.batteryLevel"):
            entities.append(UhomeBatterySensorEntity(coordinator, device_id))
    
    async_add_entities(entities)


class UhomeBatterySensorEntity(CoordinatorEntity, SensorEntity):
    """Representation of a Uhome battery sensor."""

    _attr_device_class = SensorDeviceClass.BATTERY
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator: UhomeDataUpdateCoordinator, device_id: str) -> None:
        """Initialize the battery sensor."""
        super().__init__(coordinator)
        self._device = coordinator.devices[device_id]
        self._attr_unique_id = f"{DOMAIN}_battery_{device_id}"
        self._attr_name = f"{self._device.name} Battery"
        self._attr_device_info = self._device.device_info

    @property
    def native_value(self) -> int | None:
        """Return battery level."""
        return self._device.battery_level
    
    @property
    def extra_state_attributes(self) -> str | None:
        """Return additional state attributes."""
        return self._device.battery_status