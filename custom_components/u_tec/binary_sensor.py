"""Support for Uhome Door Sensors."""
import logging
from typing import cast

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from utec_py.devices.lock import Lock as UhomeLock

from .const import DOMAIN, SIGNAL_NEW_DEVICE
from .coordinator import UhomeDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Uhome door sensors based on a config entry."""
    coordinator: UhomeDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]

    added_entity_ids: set[str] = set()

    def _create_entities(add_only_new: bool = False) -> list[UhomeDoorSensor]:
        entities = []
        for device_id, device in coordinator.devices.items():
            if not isinstance(device, UhomeLock) or not device.has_door_sensor:
                continue
            unique_id = f"{DOMAIN}_door_{device_id}"
            if add_only_new and unique_id in added_entity_ids:
                continue
            entities.append(UhomeDoorSensor(coordinator, device_id))
            added_entity_ids.add(unique_id)
        return entities

    async_add_entities(_create_entities())

    def _async_add_new_entities() -> None:
        async_add_entities(_create_entities(add_only_new=True))

    entry.async_on_unload(
        async_dispatcher_connect(hass, SIGNAL_NEW_DEVICE, _async_add_new_entities)
    )


class UhomeDoorSensor(CoordinatorEntity, BinarySensorEntity):
    """Representation of a Uhome door sensor."""

    _attr_device_class = BinarySensorDeviceClass.DOOR

    def __init__(self, coordinator: UhomeDataUpdateCoordinator, device_id: str) -> None:
        """Initialize the door sensor."""
        super().__init__(coordinator)
        self._device = cast(UhomeLock, coordinator.devices[device_id])
        self._attr_unique_id = f"{DOMAIN}_door_{device_id}"
        self._attr_name = f"{self._device.name} Door"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._device.device_id)},
            name=self._device.name,
            manufacturer=self._device.manufacturer,
            model=self._device.model,
            hw_version=self._device.hw_version,
        )

    @property
    def available(self) -> bool:
        """Return True if entity is available.

        Unavailable only when the device is offline or two consecutive polls failed.
        """
        return self.coordinator.poll_healthy_enough and self._device.available

    @property
    def is_on(self) -> bool | None:
        """Return true if the door is open."""
        return self._device.is_door_open
