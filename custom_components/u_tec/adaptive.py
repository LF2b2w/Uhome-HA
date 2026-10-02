"""Adaptive Aggressive confirmation polling for a single lock.

Standalone from Home Assistant entity code so the burst rules can be unit
tested without loading lock.py. The coordinator owns one AdaptivePoller.

After a lock or unlock command, poll only that device on a Fibonacci delay
(1, 2, 3, 5, 8 seconds) until the API reports the commanded state. Stop at
5 attempts, or when the next delay would be >= the idle scan interval.

A confirmed burst records a confirmation. A later poll or push that
contradicts that confirmation inside one idle interval (capped at 60s)
is not applied. Instead the burst is re-armed and the fresh poll wins,
so a stale cloud read cannot silently undo a lock, and a real bolt
failure is not hidden. A new command clears that confirmation: the
command is newer evidence than the previous mark.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_call_later
from homeassistant.util import dt as dt_util

from .const import (
    ADAPTIVE_AGGRESSIVE_INITIAL_DELAY,
    ADAPTIVE_AGGRESSIVE_MAX_ATTEMPTS,
    CONFIRMATION_WINDOW_CAP,
    DEFAULT_SCAN_INTERVAL,
    EVENT_LOCK_COMMAND_FAILED,
    SIGNAL_ADAPTIVE_POLL,
)
from .optimistic import is_adaptive_aggressive_enabled

_LOGGER = logging.getLogger(__name__)

LOCK_CAPABILITY = "st.lock"
LOCK_ATTRIBUTE = "lockState"
_LOGGER = logging.getLogger(__name__)


def next_fibonacci_delay(delay: int, prev_delay: int) -> int:
    """Return the next Fibonacci backoff step.

    prev_delay starts equal to the initial delay so the sequence is
    1, 2, 3, 5, 8 rather than 1, 1, 2, 3, 5.
    """
    return int(delay) + int(prev_delay)


def confirmation_delays(max_attempts: int = ADAPTIVE_AGGRESSIVE_MAX_ATTEMPTS) -> list[int]:
    """Return the Fibonacci delays a burst will use, from the constants."""
    delay = ADAPTIVE_AGGRESSIVE_INITIAL_DELAY
    prev = delay
    seen = [delay]
    for _ in range(max(0, max_attempts - 1)):
        nxt = next_fibonacci_delay(delay, prev)
        seen.append(nxt)
        prev, delay = delay, nxt
    return seen
    """Return the next Fibonacci backoff step.

    prev_delay starts equal to the initial delay so the sequence is
    1, 2, 3, 5, 8 rather than 1, 1, 2, 3, 5.
    """
    return int(delay) + int(prev_delay)


def reported_locked(state_data: Any) -> bool | None:
    """Return the lock state only when the payload actually carries it.

    Lock.is_locked falls back to False when st.lock is missing, which is
    indistinguishable from a real unlock. Battery and door pushes must not
    confirm a burst.
    """
    if not isinstance(state_data, dict):
        return None
    cap = state_data.get(LOCK_CAPABILITY)
    if not isinstance(cap, dict) or LOCK_ATTRIBUTE not in cap:
        return None
    value = cap[LOCK_ATTRIBUTE]
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.lower()
        if lowered == "locked":
            return True
        if lowered == "unlocked":
            return False
    return None


def iter_device_payloads(response: Any):
    """Yield device dicts from nested or flat U-Tec replies.

    Production has returned both {"payload": {"devices": [...]}} and a
    top-level list (issue #30). A flat list must not silently burn attempts.
    """
    if isinstance(response, list):
        yield from (item for item in response if isinstance(item, dict))
        return
    if not isinstance(response, dict):
        return
    payload = response.get("payload", response)
    if isinstance(payload, list):
        yield from (item for item in payload if isinstance(item, dict))
        return
    if isinstance(payload, dict):
        devices = payload.get("devices", [])
        if isinstance(devices, list):
            yield from (item for item in devices if isinstance(item, dict))


class AdaptivePoller:
    """Per-device Fibonacci confirmation bursts (1, 2, 3, 5, 8s)."""

    def __init__(self, coordinator) -> None:
        self.coordinator = coordinator
        self._bursts: dict[str, dict[str, Any]] = {}
        self._confirmations: dict[str, dict[str, Any]] = {}
        self._ticks: dict[str, Any] = {}

    def idle_interval_seconds(self) -> int:
        interval = self.coordinator.update_interval
        if interval is None:
            return DEFAULT_SCAN_INTERVAL
        return max(1, int(interval.total_seconds()))

    def confirmation_window_seconds(self) -> int:
        """How long a confirmed state is protected from a contradicting report."""
        return min(CONFIRMATION_WINDOW_CAP, self.idle_interval_seconds())

    def cancel(
        self,
        device_id: str,
        reason: str,
        *,
        burst: dict[str, Any] | None = None,
        notify: bool = False,
    ) -> None:
        current = self._bursts.get(device_id)
        if current is None:
            return
        if burst is not None and current is not burst:
            return
        self._bursts.pop(device_id, None)
        unsub = current.get("unsub")
        if unsub:
            unsub()
            current["unsub"] = None
        attempts = int(current.get("attempt", 0))
        _LOGGER.debug(
            "Adaptive aggressive stopped for %s after %s attempt(s): %s",
            device_id,
            attempts,
            reason,
        )
        if notify:
            self._signal_unconfirmed(device_id, current, reason, attempts)

    def cancel_all(self, reason: str = "unload") -> None:
        for device_id in list(self._bursts):
            self.cancel(device_id, reason)
        self._confirmations.clear()
        for device_id, task in list(self._ticks.items()):
            cancel = getattr(task, "cancel", None)
            if cancel:
                cancel()
            self._ticks.pop(device_id, None)

    def is_running(self, device_id: str) -> bool:
        return device_id in self._bursts

    def expected_locked(self, device_id: str) -> bool | None:
        burst = self._bursts.get(device_id)
        if burst is None:
            return None
        return bool(burst["expected_locked"])

    def start(
        self,
        device_id: str,
        expected_locked: bool,
        *,
        clear_confirmation: bool = True,
    ) -> None:
        # A new command is newer evidence than the previous confirmation.
        # A re-arm keeps the confirmation it is defending.
        if clear_confirmation:
            self._confirmations.pop(device_id, None)
        idle = self.idle_interval_seconds()
        initial = ADAPTIVE_AGGRESSIVE_INITIAL_DELAY
        if initial >= idle:
            _LOGGER.debug(
                "Adaptive aggressive not started for %s: initial delay %ss >= idle %ss",
                device_id,
                initial,
                idle,
            )
            return

        if device_id in self._bursts:
            self.cancel(device_id, "restarted")

        self._bursts[device_id] = {
            "expected_locked": expected_locked,
            "attempt": 0,
            "delay": initial,
            "prev_delay": initial,
            "unsub": None,
        }
        _LOGGER.debug(
            "Adaptive aggressive started for %s: expected_locked=%s idle=%ss",
            device_id,
            expected_locked,
            idle,
        )
        self._schedule(device_id, initial)

    def young_confirmation(self, device_id: str) -> dict[str, Any] | None:
        mark = self._confirmations.get(device_id)
        if mark is None:
            return None
        age = (dt_util.utcnow() - mark["at"]).total_seconds()
        if age > self.confirmation_window_seconds():
            self._confirmations.pop(device_id, None)
            return None
        return mark

    def contradicts_confirmation(self, device_id: str, state_data: Any) -> bool:
        """Return True when a report disagrees with a young confirmation."""
        mark = self.young_confirmation(device_id)
        observed = reported_locked(state_data)
        if mark is None or observed is None:
            return False
        return observed != mark["locked"]

    def _adaptive_enabled(self, device_id: str) -> bool:
        entry = getattr(self.coordinator, "config_entry", None)
        options = getattr(entry, "options", None) or {}
        return is_adaptive_aggressive_enabled(options, device_id)

    def rearm_for_confirmation(self, device_id: str) -> None:
        """Fetch fresh evidence instead of applying a contradicting report."""
        if not self._adaptive_enabled(device_id):
            self._confirmations.pop(device_id, None)
            return
        mark = self.young_confirmation(device_id)
        if mark is None:
            return
        _LOGGER.debug(
            "Adaptive aggressive re-arming %s: report contradicted confirmed locked=%s",
            device_id,
            mark["locked"],
        )
        self.start(device_id, bool(mark["locked"]), clear_confirmation=False)

    def cancel_if_confirmed(
        self,
        device_id: str,
        device,
        reason: str = "confirmed",
        state_data: Any = None,
    ) -> None:
        burst = self._bursts.get(device_id)
        if burst is None:
            return
        payload = device.get_state_data() if state_data is None else state_data
        observed = reported_locked(payload)
        if observed is None or observed != burst["expected_locked"]:
            return
        self._confirmations[device_id] = {
            "locked": observed,
            "at": dt_util.utcnow(),
        }
        self.cancel(device_id, reason, burst=burst)

    def _schedule(self, device_id: str, delay: int) -> None:
        burst = self._bursts.get(device_id)
        if burst is None:
            return
        previous = burst.get("unsub")
        if previous:
            previous()
            burst["unsub"] = None

        async def _fire(_now) -> None:
            task = asyncio.current_task()
            if task is not None:
                self._ticks[device_id] = task
            try:
                await self.async_tick(device_id)
            finally:
                if task is not None and self._ticks.get(device_id) is task:
                    self._ticks.pop(device_id, None)

        burst["unsub"] = async_call_later(self.coordinator.hass, delay, _fire)

    def _signal_unconfirmed(
        self,
        device_id: str,
        burst: dict[str, Any],
        reason: str,
        attempts: int,
    ) -> None:
        _LOGGER.warning(
            "Adaptive aggressive gave up for %s after %s attempt(s): %s",
            device_id,
            attempts,
            reason,
        )
        bus = self.coordinator.hass.bus
        bus.async_fire(
                EVENT_LOCK_COMMAND_FAILED,
                {
                    "device_id": device_id,
                    "expected_locked": burst.get("expected_locked"),
                    "attempts": attempts,
                    "reason": reason,
                },
            )

    async def async_tick(self, device_id: str) -> None:
        """Run one poll after the Adaptive Aggressive timer ends."""
        burst = self._bursts.get(device_id)
        if burst is None:
            return

        burst["unsub"] = None
        burst["attempt"] = int(burst["attempt"]) + 1
        delay = int(burst["delay"])
        expected = bool(burst["expected_locked"])
        _LOGGER.debug(
            "Adaptive aggressive timer ended for %s: attempt %s/%s after %ss",
            device_id,
            burst["attempt"],
            ADAPTIVE_AGGRESSIVE_MAX_ATTEMPTS,
            delay,
        )

        device = self.coordinator.devices.get(device_id)
        if device is None:
            self.cancel(device_id, "device gone", burst=burst)
            return

        confirmed = False
        try:
            response = await self.coordinator.api.get_device_state([device_id], None)
            if self._bursts.get(device_id) is not burst:
                return
            self.coordinator.raise_for_error_payload(response)
            for device_data in iter_device_payloads(response):
                if device_data.get("id") == device_id:
                    await device.update_state_data(device_data)
                    break
            actual = reported_locked(device.get_state_data())
            _LOGGER.debug(
                "Adaptive aggressive result for %s: locked=%s expected=%s",
                device_id,
                actual,
                expected,
            )
            async_dispatcher_send(
                self.coordinator.hass,
                f"{SIGNAL_ADAPTIVE_POLL}_{device_id}",
                device.get_state_data(),
            )
            confirmed = actual is not None and actual == expected
        except ConfigEntryAuthFailed:
            if self._bursts.get(device_id) is burst:
                self.cancel(device_id, "auth failed", burst=burst, notify=True)
            return
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning(
                "Adaptive aggressive poll failed for %s: %s",
                device_id,
                type(err).__name__,
            )

        if self._bursts.get(device_id) is not burst:
            return

        if confirmed:
            snapshot = device.get_state_data()
            current = dict(self.coordinator.data) if self.coordinator.data else {}
            current[device_id] = snapshot
            self.coordinator.async_set_updated_data(current)
            self._confirmations[device_id] = {
                "locked": expected,
                "at": dt_util.utcnow(),
            }
            self.cancel(device_id, "confirmed", burst=burst)
            return

        if burst["attempt"] >= ADAPTIVE_AGGRESSIVE_MAX_ATTEMPTS:
            self.cancel(device_id, "max attempts", burst=burst, notify=True)
            return

        prev_delay = int(burst.get("prev_delay", delay))
        next_delay = next_fibonacci_delay(delay, prev_delay)
        idle = self.idle_interval_seconds()
        if next_delay >= idle:
            self.cancel(device_id, "idle cap", burst=burst, notify=True)
            return

        burst["prev_delay"] = delay
        burst["delay"] = next_delay
        self._schedule(device_id, next_delay)
