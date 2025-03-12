"""Support for Uhome locks."""

from homeassistant.components.lock import LockEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import _LOGGER, HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from utec_py.devices.lock import Lock as UhomeLock
from utec_py.exceptions import DeviceError

from .const import DOMAIN
from .coordinator import UhomeDataUpdateCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Uhome lock based on a config entry."""
    coordinator: UhomeDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id][
        "coordinator"
    ]

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
        self._attr_has_entity_name = True

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self.coordinator.last_update_success and self._device.available

    @property
    def is_locked(self) -> bool:
        """Return true if the lock is locked."""
        return self._device.is_locked

    @property
    def is_open(self) -> bool:
        """Return true if the lock is open."""
        return self._device.is_open

    @property
    def is_jammed(self) -> bool:
        """Return true if the lock is jammed."""
        return self._device.is_jammed

    @property
    def extra_state_attributes(self) -> dict[str, any]:
        """Return the state attributes of the lock."""
        # Get values and ensure they're not sequences
        lock_state = self._device.lock_state
        door_state = self._device.door_state

        # Only include lock_mode if has_door_sensor is True
        attributes = {
            "lock_state": str(lock_state) if lock_state is not None else None,
            "door_state": str(door_state) if door_state is not None else None,
        }

        # Add lock_mode conditionally
        if self._device.has_door_sensor:
            lock_mode = self._device.lock_mode
            attributes["lock_mode"] = str(lock_mode) if lock_mode is not None else None

        return attributes

    async def async_lock(self) -> None:
        """Lock the device."""
        try:
            await self._device.lock()
            await self.coordinator.async_request_refresh()
        except DeviceError as err:
            _LOGGER.error("Failed to lock device %s: %s", self._device.device_id, err)
            raise HomeAssistantError("Failed to lock: {err}") from err

    async def async_unlock(self) -> None:
        """Unlock the device."""
        try:
            await self._device.unlock()
            await self.coordinator.async_request_refresh()
        except DeviceError as err:
            _LOGGER.error("Failed to unlock device %s: %s", self._device.device_id, err)
            raise HomeAssistantError("Failed to unlock: {err}") from err
