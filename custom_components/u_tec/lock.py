"""Support for Uhome locks."""

from utec_py.devices.lock import Lock as UhomeLock
from voluptuous import Any

from homeassistant.components.lock import LockEntity
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
    """Set up Uhome lock based on a config entry."""
    coordinator: UhomeDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]

    # Add all locks
    async_add_entities(
        UhomeLockEntity(coordinator, device_id)
        for device_id, device in coordinator.devices.items()
        if isinstance(device, UhomeLock)
    )


class UhomeLockEntity(CoordinatorEntity, LockEntity):
    """Representation of a Uhome lock."""

    def __init__(self, coordinator: UhomeDataUpdateCoordinator, device_id: str) -> None:
        """Initialize the lock."""
        super().__init__(coordinator)
        self._device = coordinator.devices[device_id]
        self._attr_unique_id = f"{DOMAIN}_{device_id}"
        self._attr_name = self._device.name
        self._attr_device_info = self._device.device_info

    @property
    def is_locked(self) -> bool:
        """Return true if the lock is locked."""
        return self._device.is_locked

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self.coordinator.last_update_success | self._device.available

    async def async_lock(self) -> None:
        """Lock the device."""
        await self._device.lock()
        await self.coordinator.async_request_refresh()

    async def async_unlock(self) -> None:
        """Unlock the device."""
        await self._device.unlock()
        await self.coordinator.async_request_refresh()
