# custom_components/utec/lock.py
"""Support for U-Tec locks."""
from homeassistant.components.lock import LockEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
import logging

from const import DOMAIN
from discovery.api import UTecAPIError

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up U-Tec lock based on a config entry."""
    coordinator = hass.data[DOMAIN][entry.entry_id]

    locks = []
    for device_id, device_data in coordinator.data.items():
        if device_data.get("category") == "LOCK":
            locks.append(UTecLock(coordinator, device_id))

    async_add_entities(locks)

class UTecLock(CoordinatorEntity, LockEntity):
    """Representation of a U-Tec lock."""

    def __init__(self, coordinator, device_id):
        """Initialize the lock."""
        super().__init__(coordinator)
        self._device_id = device_id
        self._attr_unique_id = device_id

    @property
    def device_info(self):
        """Return device information."""
        device_data = self.coordinator.data[self._device_id]
        return {
            "identifiers": {(DOMAIN, self._device_id)},
            "name": device_data["name"],
            "manufacturer": device_data["deviceInfo"]["manufacturer"],
            "model": device_data["deviceInfo"]["model"],
            "hw_version": device_data["deviceInfo"]["hwVersion"],
        }

    @property
    def name(self):
        """Return the name of the lock."""
        return self.coordinator.data[self._device_id]["name"]

    @property
    def is_locked(self):
        """Return true if lock is locked."""
        states = self.coordinator.data[self._device_id]["state"]["states"]
        return any(
            state["capability"] == "st.Lock"
            and state["name"] == "lockState"
            and state["value"] == "locked"
            for state in states
        )

    @property
    def battery_level(self):
        """Return the battery level of the lock."""
        states = self.coordinator.data[self._device_id]["state"]["states"]
        for state in states:
            if (state["capability"] == "st.BatteryLevel"
                and state["name"] == "level"):
                return state["value"]
        return None

    async def async_lock(self, **kwargs):
        """Lock the device."""
        try:
            await self.coordinator.api.lock_device(self._device_id)
            await self.coordinator.async_request_refresh()
        except UTecAPIError as err:
            _LOGGER.error("Failed to lock device %s: %s", self._device_id, err)
            raise

    async def async_unlock(self, **kwargs):
        """Unlock the device."""
        try:
            await self.coordinator.api.unlock_device(self._device_id)
            await self.coordinator.async_request_refresh()
        except UTecAPIError as err:
            _LOGGER.error("Failed to unlock device %s: %s", self._device_id, err)
            raise