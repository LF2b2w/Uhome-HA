"""Support for Uhome locks."""

import logging
from datetime import datetime
from typing import Any, cast

from homeassistant.components.lock import LockEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util
from utec_py.devices.lock import Lock as UhomeLock
from utec_py.exceptions import DeviceError

from .const import (
    CONF_OPTIMISTIC_LOCKS,
    DOMAIN,
    OPTIMISTIC_TIMEOUT,
    SIGNAL_DEVICE_UPDATE,
    is_optimistic_enabled,
    push_asserts_state,
)
from .coordinator import UhomeDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

# OPTIMISTIC_TIMEOUT lives in const.py because light.py and switch.py share
# the same bounding. Only the lock path was reproduced on real hardware (an
# ULTRALOQ Latch-5-F, whose non-disableable auto-lock guarantees the pin);
# the light/switch fixes mirror this logic but are unverified on live
# hardware. https://github.com/LF2b2w/Uhome-HA/issues/58

# utec_py maps LockMode.PASSAGE -> "Passage" (devices/lock.py::lock_mode).
# In this mode the device ignores lock/unlock commands outright.
PASSAGE_MODE = "Passage"


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
    _optimistic_set_at: datetime | None = None
    _force_next_write: bool = False

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
        self._optimistic_set_at: datetime | None = None
        self._force_next_write = False

    @property
    def force_update(self) -> bool:
        """Return True to write state even when it has not changed.

        Entity._async_write_ha_state passes this to the state machine, which
        skips the state-changed event when the new state is identical unless
        force_update is set. Toggling it around a single write therefore emits
        a real event for an otherwise-identical state. See _resync_listeners.
        """
        return self._force_next_write

    def _resync_listeners(self) -> None:
        """Re-emit the current (unchanged) state as a real state event.

        In Passage mode a lock command changes nothing, so no state event would
        fire. Consumers that only recompute on a state change never learn the
        command was a no-op -- HA's HomeKit bridge, for one, recomputes its
        lock target characteristic in async_update_state, which runs only on a
        state event, so its tile sticks on "Locking..." indefinitely.
        Re-asserting the true state gives them an event to act on without
        publishing anything false.

        This relies on Entity._async_write_ha_state reading force_update
        synchronously during the write (it passes the value straight into the
        state machine, which suppresses the state-changed event for an
        identical state unless force_update is set). That is verified against
        current HA internals, not a contractual API: if a future HA version
        caches force_update at registration or defers the write, this toggle
        would silently stop emitting the event. The finally-reset and
        test_force_update_reset_even_if_write_raises guard the toggle itself.
        """
        self._force_next_write = True
        try:
            self.async_write_ha_state()
        finally:
            self._force_next_write = False

    def _is_optimistic(self) -> bool:
        """Return True if optimistic updates apply to this device.

        Passage mode ignores lock/unlock commands, so a new optimistic state
        would always be wrong there; report the polled truth instead.
        Optimism outstanding from before the mode changed is dropped in
        _handle_coordinator_update rather than here, so that is_locked and
        assumed_state cannot disagree.
        """
        if self._device.lock_mode == PASSAGE_MODE:
            return False
        return is_optimistic_enabled(
            self.coordinator.config_entry.options,
            CONF_OPTIMISTIC_LOCKS,
            self._device.device_id,
        )

    @property
    def available(self) -> bool:
        """Return True if entity is available.

        Unavailable only when the device itself is offline, or the coordinator
        has failed two consecutive API polls (a single transient failure is
        tolerated).
        """
        return self.coordinator.poll_healthy_enough and self._device.available

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
        """Return True if the current reported state is optimistic and unconfirmed."""
        return self._is_optimistic() and self._optimistic_is_locked is not None

    def _handle_coordinator_update(self) -> None:
        """Handle updated data from coordinator, clearing optimistic state.

        Lock/unlock commands are slow (physical deadbolt movement) so we do not
        clear the optimistic state on the first poll, which may still return the
        old value. But we cannot wait forever either: if the device never
        reaches the commanded state the entity would stay wrong indefinitely.
        So optimism is held for OPTIMISTIC_TIMEOUT and then released.
        """
        if self._optimistic_is_locked is not None:
            if self._device.lock_mode == PASSAGE_MODE:
                # The lock entered Passage mode while optimism was outstanding.
                # It will never confirm, and _is_optimistic() now reports False,
                # so holding on would make is_locked return an assumed value
                # while assumed_state claims it is confirmed. Drop it now.
                self._optimistic_is_locked = None
                self._optimistic_set_at = None
            elif self._optimistic_is_locked == self._device.is_locked:
                self._optimistic_is_locked = None
                self._optimistic_set_at = None
            elif self._optimistic_set_at is None:
                # Optimistic value with no timestamp: start the clock now
                # rather than clearing, so the grace period is preserved.
                self._optimistic_set_at = dt_util.utcnow()
            elif dt_util.utcnow() - self._optimistic_set_at > OPTIMISTIC_TIMEOUT:
                _LOGGER.debug(
                    "Optimistic state for %s unconfirmed after %s; trusting device",
                    self._device.device_id,
                    OPTIMISTIC_TIMEOUT,
                )
                self._optimistic_is_locked = None
                self._optimistic_set_at = None
            # else: still within the grace period while the bolt moves
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
                self._optimistic_set_at = dt_util.utcnow()
                self.async_write_ha_state()
            elif self._device.lock_mode == PASSAGE_MODE:
                # Passage mode ignores the command, so no state change will
                # follow and HomeKit would hang on "Locking...". Re-assert the
                # true state so the bridge resets its target characteristic.
                _LOGGER.debug(
                    "%s is in Passage mode; lock command ignored, resyncing"
                    " listeners with the unchanged state",
                    self._device.device_id,
                )
                self._resync_listeners()
        except DeviceError as err:
            _LOGGER.error("Failed to lock device %s: %s", self._device.device_id, err)
            raise HomeAssistantError(f"Failed to lock: {err}") from err

    async def async_unlock(self, **kwargs: Any) -> None:
        """Unlock the device.

        Deliberately has no Passage-mode resync counterpart to async_lock: a
        lock in Passage mode already reports itself unlocked, so an unlock
        command leaves consumers' target and current states in agreement and
        nothing can hang. Only the lock direction can diverge.
        """
        _LOGGER.debug("Unlocking device %s", self._device.device_id)
        try:
            await self._device.unlock()
            if self._is_optimistic():
                self._optimistic_is_locked = False
                self._optimistic_set_at = dt_util.utcnow()
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
        """Update device from push data, clearing optimistic state on disagreement.

        By the time this fires, the coordinator has already applied the push to
        the device (coordinator.update_push_data calls device.update_state_data
        before dispatching), so self._device.is_locked reflects the pushed
        state. A push that authoritatively contradicts an outstanding optimistic
        value drops the optimism immediately rather than waiting out
        OPTIMISTIC_TIMEOUT -- this corrects the #58 auto-lock case (device
        re-locks itself after an unlock) within seconds.

        We only act when the push actually carried lock state: pushes are
        full-state replaces, and Lock.is_locked falls back to False when the
        lock capability is absent, so a partial push (e.g. a door-sensor event)
        would otherwise read as a spurious "unlocked" and clear optimism
        mid-command. A push that agrees, omits lock state, or leaves it
        unchanged stays on the confirm/timeout path.
        """
        if (
            self._optimistic_is_locked is not None
            and push_asserts_state(push_data, "st.lock", "lockState")
            and self._optimistic_is_locked != self._device.is_locked
        ):
            self._optimistic_is_locked = None
            self._optimistic_set_at = None
        self.async_write_ha_state()
