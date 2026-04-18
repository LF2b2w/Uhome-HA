"""Support for Uhome locks."""

import logging
from typing import Any, cast

from homeassistant.components.lock import LockEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from utec_py.devices.lock import Lock as UhomeLock
from utec_py.exceptions import DeviceError

from .const import (
    CONF_OPTIMISTIC_LOCKS,
    DOMAIN,
    SIGNAL_DEVICE_UPDATE,
    is_optimistic_enabled,
)
from .coordinator import UhomeDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Uhome lock based on a config entry."""
    coordinator: UhomeDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id][
        "coordinator"
    ]

    async_add_entities(
        UhomeLockEntity(coordinator, device_id)
        for device_id, device in coordinator.devices.items()
        if isinstance(device, UhomeLock)
    )


class UhomeLockEntity(CoordinatorEntity, LockEntity):
    """Representation of a Uhome lock."""

    _optimistic_is_locked: bool | None = None

    def __init__(self, coordinator: UhomeDataUpdateCoordinator, device_id: str) -> None:
        """Initialize the lock."""
        super().__init__(coordinator)
        self._device = cast(UhomeLock, coordinator.devices[device_id])
        self._attr_unique_id = f"{DOMAIN}_{device_id}"
        self._attr_name = self._device.name
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._device.device_id)},
            name=self._device.name,
            manufacturer=self._device.manufacturer,
            model=self._device.model,
            hw_version=self._device.hw_version,
        )
        self._attr_has_entity_name = True
        self._optimistic_is_locked: bool | None = None

    def _is_optimistic(self) -> bool:
        """Return True if optimistic updates apply to this device."""
        return is_optimistic_enabled(
            self.coordinator.config_entry.options,
            CONF_OPTIMISTIC_LOCKS,
            self._device.device_id,
        )

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self.coordinator.last_update_success and self._device.available

    @property
    def is_locked(self) -> bool:
        """Return true if the lock is locked."""
        if self._optimistic_is_locked is not None:
            return self._optimistic_is_locked
        return self._device.is_locked

    @property
    def is_jammed(self) -> bool:
        """Return true if the lock is jammed."""
        return self._device.is_jammed

    @property
    def assumed_state(self) -> bool:
        """Return True if the current state is optimistic rather than confirmed."""
        return self._is_optimistic()

    def _handle_coordinator_update(self) -> None:
        """Handle updated data from coordinator, clearing optimistic state.

        Lock/unlock commands are slow (physical deadbolt movement) so we only
        clear the optimistic state once the device confirms the new lockState,
        rather than on the first poll which may still return the old value.
        """
        if self._optimistic_is_locked is not None:
            confirmed = (
                self._optimistic_is_locked and self._device.is_locked
                or not self._optimistic_is_locked and not self._device.is_locked
            )
            if confirmed:
                self._optimistic_is_locked = None
            # else: keep optimistic state until device catches up
        super()._handle_coordinator_update()

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the state attributes of the lock."""
        attributes = {
            "lock_state": self._device.lock_state,
            "lock_mode": self._device.lock_mode,
            "battery_level": self._device.battery_level,
            "battery_status": self._device.battery_status,
        }
        if self._device.has_door_sensor:
            attributes["door_state"] = self._device.door_state
            attributes["is_door_open"] = self._device.is_door_open
        return attributes

    async def async_lock(self, **kwargs: Any) -> None:
        """Lock the device."""
        _LOGGER.debug("Locking device %s", self._device.device_id)
        try:
            await self._device.lock()
            if self._is_optimistic():
                self._optimistic_is_locked = True
                self.async_write_ha_state()
        except DeviceError as err:
            _LOGGER.error("Failed to lock device %s: %s", self._device.device_id, err)
            raise HomeAssistantError(f"Failed to lock: {err}") from err

    async def async_unlock(self, **kwargs: Any) -> None:
        """Unlock the device."""
        _LOGGER.debug("Unlocking device %s", self._device.device_id)
        try:
            await self._device.unlock()
            if self._is_optimistic():
                self._optimistic_is_locked = False
                self.async_write_ha_state()
        except DeviceError as err:
            _LOGGER.error("Failed to unlock device %s: %s", self._device.device_id, err)
            raise HomeAssistantError(f"Failed to unlock: {err}") from err

    async def async_added_to_hass(self):
        """Register callbacks."""
        await super().async_added_to_hass()

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
