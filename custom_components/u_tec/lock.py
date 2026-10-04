"""Support for Uhome locks."""

import asyncio
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
from utec_client.devices.lock import Lock as UhomeLock
from utec_client.exceptions import DeviceError

from .adaptive import iter_device_payloads
from .const import (
    CONF_OPTIMISTIC_LOCKS,
    DOMAIN,
    OPTIMISTIC_TIMEOUT,
    PASSAGE_VERIFY_TIMEOUT,
    SIGNAL_ADAPTIVE_POLL,
    SIGNAL_DEVICE_UPDATE,
    is_adaptive_aggressive_enabled,
    is_optimistic_enabled,
    push_asserts_state,
)
from .coordinator import UhomeDataUpdateCoordinator
from .debug_polling import debug_polling_active
from .stats import SKIP_PASSAGE_MODE

_LOGGER = logging.getLogger(__name__)

# OPTIMISTIC_TIMEOUT lives in const.py because light.py and switch.py share
# the same bounding. Only the lock path was reproduced on real hardware (an
# ULTRALOQ Latch-5-F, whose non-disableable auto-lock guarantees the pin);
# the light/switch fixes mirror this logic but are unverified on live
# hardware. https://github.com/LF2b2w/Uhome-HA/issues/58

# SECURITY COMMANDS ARE NEVER RECOMMENDATIONS. Lock and unlock (and any
# future Passage or mode command) are always sent, or verified first against
# the authoritative source (a fresh query of that lock). They are never
# skipped because of cached or perceived state: not "already locked", not a
# stale lock mode, not debug polling, optimistic state, Adaptive Aggressive,
# or failing polls. That is also why the entity stays available: Home
# Assistant silently drops service calls to unavailable entities.

# utec_client maps LockMode.PASSAGE -> "Passage" (devices/lock.py::lock_mode).
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
    _passage_unverified: bool = False
    _passage_check_error: str | None = None

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
        # Set when a cached Passage mode could not be confirmed and the lock
        # command went out anyway; treat the lock as Normal until fresh data.
        self._passage_unverified = False

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
        if self._in_passage_mode():
            return False
        if debug_polling_active(self.coordinator):
            return False
        return is_optimistic_enabled(
            self.coordinator.config_entry.options,
            CONF_OPTIMISTIC_LOCKS,
            self._device.device_id,
        )

    def _start_adaptive_if_enabled(self, expected_locked: bool) -> None:
        """Kick an Adaptive Aggressive confirmation burst after a command."""
        if self._in_passage_mode():
            return
        if not is_adaptive_aggressive_enabled(
            self.coordinator.config_entry.options,
            self._device.device_id,
        ):
            return
        self.coordinator.start_adaptive_poll(self._device.device_id, expected_locked)

    def _in_passage_mode(self) -> bool:
        """Cached Passage mode, unless a lock command just went out because
        that cache could not be confirmed."""
        return self._device.lock_mode == PASSAGE_MODE and not self._passage_unverified

    async def _fresh_passage_check(self) -> bool | None:
        """Ask the API for this lock's current mode, once.

        Returns True when the fresh state confirms Passage, False when it
        shows another mode, and None when it could not be verified (error,
        timeout, error envelope, or no lock mode in the reply). Counted as a
        query in API accounting because it goes through the metered client.
        """
        device_id = self._device.device_id
        try:
            response = await asyncio.wait_for(
                self.coordinator.api.query_device(device_id),
                PASSAGE_VERIFY_TIMEOUT,
            )
            self.coordinator.raise_for_error_payload(response)
        except Exception as err:  # noqa: BLE001
            self._passage_check_error = type(err).__name__
            return None
        for device_data in iter_device_payloads(response):
            if device_data.get("id") != device_id:
                continue
            states = device_data.get("states")
            has_mode = isinstance(states, list) and any(
                isinstance(s, dict)
                and s.get("capability") == "st.lock"
                and s.get("name") == "lockMode"
                for s in states
            )
            if not has_mode:
                break
            await self._device.update_state_data(device_data)
            return self._device.lock_mode == PASSAGE_MODE
        self._passage_check_error = "no lock mode in reply"
        return None

    @property
    def available(self) -> bool:
        """Always True, so lock and unlock are never dropped.

        Home Assistant skips service calls to unavailable entities without
        telling anyone. Basing that on cached health (two failed polls, or
        the last status saying offline) would silently drop a security
        command. Instead the state reads unknown while the status cannot be
        trusted, and a command still goes to the API, which reports a real
        failure if the lock cannot be reached.
        """
        return True

    @property
    def _status_trusted(self) -> bool:
        """Polls are healthy and the last status said the lock is online."""
        return bool(self.coordinator.poll_healthy_enough and self._device.available)

    @property
    def is_locked(self) -> bool:
        """Return true if the lock is locked; None (unknown) if status is stale."""
        if self._optimistic_is_locked is not None:
            return self._optimistic_is_locked
        if not self._status_trusted:
            return None
        return self._device.is_locked

    @property
    def is_jammed(self) -> bool:
        """Return true if the lock is jammed; None (unknown) if status is stale."""
        if not self._status_trusted:
            return None
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
        # Fresh data has arrived; trust the reported lock mode again.
        self._passage_unverified = False
        if self._optimistic_is_locked is not None:
            if debug_polling_active(self.coordinator):
                # Debug polling shows raw polled state only.
                self._optimistic_is_locked = None
                self._optimistic_set_at = None
            elif self._device.lock_mode == PASSAGE_MODE:
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
            # False while polls are failing or the lock last reported
            # offline. The state then reads unknown, but commands still go.
            "status_current": self._status_trusted,
        }
        if self._device.has_door_sensor:
            attributes["door_state"] = self._device.door_state
            attributes["is_door_open"] = self._device.is_door_open
        return attributes

    def _log_if_status_stale(self, command: str, name: str) -> None:
        if not self._status_trusted:
            _LOGGER.info(
                "%s: sending %s command although the last status is not current"
                " (polls failing or lock reported offline)",
                name,
                command,
            )

    # Command handlers. Security commands are never recommendations: send,
    # or verify with a fresh query first. Never skip on cached state.
    async def async_lock(self, **kwargs: Any) -> None:
        """Lock the device.

        A lock in Passage mode ignores a lock command. When the cached mode
        says Passage, one fresh single-device query checks it first. Only a
        fresh confirmation skips the command: no command call, no optimistic
        state, no Adaptive Aggressive burst, and listeners are resynced with
        the unchanged state so HomeKit does not hang on "Locking...". If the
        fresh state is not Passage, or the check fails or times out, the
        command is sent as usual. When in doubt, send the command.
        """
        name = self._device.name or self._device.device_id
        self._log_if_status_stale("lock", name)
        self._passage_unverified = False
        if self._device.lock_mode == PASSAGE_MODE:
            self._passage_check_error = None
            confirmed = await self._fresh_passage_check()
            if confirmed:
                _LOGGER.warning(
                    "%s is in Passage mode (confirmed by a fresh status check);"
                    " lock command not sent (the lock would ignore it),"
                    " Adaptive Aggressive skipped",
                    name,
                )
                self.coordinator.stats.record_command_skipped(
                    SKIP_PASSAGE_MODE, self._device.device_id
                )
                self._resync_listeners()
                return
            if confirmed is False:
                _LOGGER.info(
                    "%s: cached Passage mode was stale (fresh status: %s);"
                    " sending lock command",
                    name,
                    self._device.lock_mode,
                )
            else:
                self._passage_unverified = True
                _LOGGER.info(
                    "%s: cached Passage mode could not be verified (%s);"
                    " sending lock command anyway",
                    name,
                    self._passage_check_error,
                )
        _LOGGER.debug("Locking device %s", self._device.device_id)
        try:
            await self._device.lock()
            self._start_adaptive_if_enabled(True)
            if self._is_optimistic():
                self._optimistic_is_locked = True
                self._optimistic_set_at = dt_util.utcnow()
                self.async_write_ha_state()
        except DeviceError as err:
            _LOGGER.error("Failed to lock device %s: %s", self._device.device_id, err)
            raise HomeAssistantError(f"Failed to lock: {err}") from err

    async def async_unlock(self, **kwargs: Any) -> None:
        """Unlock the device. Always sent, even if the cache says unlocked.

        Deliberately has no Passage-mode resync counterpart to async_lock: a
        lock in Passage mode already reports itself unlocked, so an unlock
        command leaves consumers' target and current states in agreement and
        nothing can hang. Only the lock direction can diverge.
        """
        self._log_if_status_stale("unlock", self._device.name or self._device.device_id)
        _LOGGER.debug("Unlocking device %s", self._device.device_id)
        try:
            await self._device.unlock()
            self._start_adaptive_if_enabled(False)
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
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                f"{SIGNAL_ADAPTIVE_POLL}_{self._device.device_id}",
                self._handle_adaptive_poll,
            )
        )

    @callback
    def _handle_adaptive_poll(self, _poll_data):
        """Apply a burst poll without the immediate optimistic clear of a push.

        Burst polls are fresh API reads, not pushes. Clearing optimism on the
        first mismatch would flicker locked→unlocked→locked while the bolt moves.
        The coordinator grace period still applies.
        """
        self._handle_coordinator_update()

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
