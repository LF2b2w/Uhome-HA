"""Support for U-tec locks."""

from utec_py_LF2b2w.devices.lock import UtecLock
from voluptuous import Any

from homeassistant.components.lock import LockEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import UHomeDeviceCoordinator, UtecEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up U-tec lock devices."""
    coordinator: UHomeDeviceCoordinator = hass.data[DOMAIN][entry.entry_id]

    locks = []
    for device_id in coordinator.device_ids:
        device = await coordinator.get_device(device_id)
        if device.get("type") == "lock":
            locks.append(UhomeLock(coordinator, device_id))

    async_add_entities(locks)


class UhomeLock(UtecEntity, LockEntity):
    """Representation of a U-tec Smart Lock."""

    def __init__(self, coordinator: UHomeDeviceCoordinator, device_id: str) -> None:
        """Initialize the lock."""
        super().__init__(self, coordinator, device_id)
        self._device_id = device_id
        self._attr_name = coordinator.data[device_id]["name"]
        self._attr_unique_id = device_id

    @property
    def is_locked(self) -> bool:
        """Return true if the lock is locked."""
        return self.coordinator.data[self._device_id]["state"].get("locked", False)

    async def async_lock(self, **kwargs: Any) -> None:
        """Lock the device."""
        await UtecLock.lock()
        await self.coordinator.async_request_refresh()

    async def async_unlock(self, **kwargs: Any) -> None:
        """Unlock the device."""
        await UtecLock.unlock()
        await self.coordinator.async_request_refresh()

    async def async_update(self) -> None:
        """Fetch new state data for the lock."""
        self._device.update_state()
