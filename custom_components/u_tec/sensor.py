"""Support for Uhome Battery Sensors."""

from typing import cast

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from utec_py.devices.device_const import DeviceCapability
from utec_py.devices.lock import Lock as UhomeLock

from .const import DOMAIN, SIGNAL_DEVICE_UPDATE, SIGNAL_NEW_DEVICE
from .coordinator import UhomeDataUpdateCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Uhome battery sensors based on a config entry."""
    coordinator: UhomeDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id][
        "coordinator"
    ]

    entities = _create_battery_entities(coordinator)
    async_add_entities(entities)

    @callback
    def async_add_sensor_entities() -> None:
        entities = _create_battery_entities(coordinator, add_only_new=True)
        async_add_entities(entities)

    entry.async_on_unload(
        async_dispatcher_connect(hass, SIGNAL_NEW_DEVICE, async_add_sensor_entities)
    )


def _create_battery_entities(coordinator, add_only_new=False):
    """Create battery entities for devices with battery capability."""
    entities = []
    for device_id, device in coordinator.devices.items():
        if hasattr(device, "has_capability") and device.has_capability(
            DeviceCapability.BATTERY_LEVEL
        ):
            # Check if this is a new device
            entity_id = f"{DOMAIN}_battery_{device_id}"
            if add_only_new and entity_id in coordinator.added_sensor_entities:
                continue

            # Add to entities list and mark as added
            entities.append(UhomeBatterySensorEntity(coordinator, device_id))
            coordinator.added_sensor_entities.add(entity_id)

    return entities


class UhomeBatterySensorEntity(CoordinatorEntity, SensorEntity):
    """Representation of a Uhome battery sensor."""

    def __init__(self, coordinator: UhomeDataUpdateCoordinator, device_id: str) -> None:
        """Initialize the battery sensor."""
        super().__init__(coordinator)
        self._device = cast(UhomeLock, coordinator.devices[device_id])
        self._attr_unique_id = f"{DOMAIN}_battery_{device_id}"
        self._attr_name = f"{self._device.name} Battery"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._device.device_id)},
            name=self._device.name,
            manufacturer=self._device.manufacturer,
            model=self._device.model,
            hw_version=self._device.hw_version,
        )
        self._attr_device_class = SensorDeviceClass.BATTERY
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_native_unit_of_measurement = PERCENTAGE

    @property
    def native_value(self) -> int | None:
        """Return battery level."""
        return self._device.battery_level

    @property
    def device_class(self) -> SensorDeviceClass | None:
        """Return device class."""
        return self._attr_device_class

    @property
    def state_class(self) -> SensorStateClass | str | None:
        """Return device state class."""
        return self._attr_state_class

    async def async_update(self) -> None:
        """Update device information."""
        await self._device.update()

    async def async_added_to_hass(self):
        """Register callbacks."""
        await super().async_added_to_hass()

        # Register update callback for push notifications
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                f"{SIGNAL_DEVICE_UPDATE}_{self._device.device_id}",
                self._handle_push_update,
            )
        )

    @callback
    def _handle_push_update(self, push_data):
        """Update device from push data."""
        self.async_write_ha_state()
