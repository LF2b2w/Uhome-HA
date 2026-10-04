"""Adaptive Aggressive confirmation polling for a single lock.

Standalone from Home Assistant entity code so the burst rules can be unit
tested without loading lock.py. The coordinator owns one AdaptivePoller.

After a lock or unlock command, poll only that device on the
ADAPTIVE_AGGRESSIVE_DELAYS schedule (1, 1, 1, 1, 2, 3, 5, 8, 13 seconds:
rapid checks easing into Fibonacci) until the API reports the commanded
state. Stop when the schedule runs out, when the next delay would be >= the
idle scan interval, or when polls keep failing (the coordinator's failure
threshold is tripped, or this burst hits that many consecutive errors).

When a burst poll is what catches the change (not a push or a regular
poll), it is logged at WARNING with the device, the new state, the seconds
since the command, and how many burst polls it took. AdaptiveStats keeps
the counts behind the Adaptive Aggressive sensors.

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
    ADAPTIVE_AGGRESSIVE_DELAYS,
    ADAPTIVE_AGGRESSIVE_INITIAL_DELAY,
    ADAPTIVE_AGGRESSIVE_MAX_ATTEMPTS,
    CONFIRMATION_WINDOW_CAP,
    DEFAULT_SCAN_INTERVAL,
    EVENT_LOCK_COMMAND_FAILED,
    MAX_CONSECUTIVE_UPDATE_FAILURES,
    SIGNAL_ADAPTIVE_POLL,
)
from .optimistic import is_adaptive_aggressive_enabled
from .stats import AA_END_CAUGHT, AA_END_POLL, AdaptiveStats

LOCK_CAPABILITY = "st.lock"
LOCK_ATTRIBUTE = "lockState"
_LOGGER = logging.getLogger(__name__)


def next_delay(attempts_done: int) -> int | None:
    """Return the delay before the next attempt, or None when the schedule ends."""
    if attempts_done >= len(ADAPTIVE_AGGRESSIVE_DELAYS):
        return None
    return ADAPTIVE_AGGRESSIVE_DELAYS[attempts_done]


def confirmation_delays(max_attempts: int = ADAPTIVE_AGGRESSIVE_MAX_ATTEMPTS) -> list[int]:
    """Return the delays a full burst will use, from the constants."""
    return list(ADAPTIVE_AGGRESSIVE_DELAYS[: max(0, max_attempts)])


def reported_locked(state_data: Any) -> bool | None:
    """Return the lock state only when the payload actually carries it.

    Lock.is_locked falls back to False when st.lock is missing, which is
    indistinguishable from a real unlock. Battery and door pushes must not
    confirm a burst.

    Accepts both shapes: the flattened {"st.lock": {"lockState": ...}} from
    Device.get_state_data(), and the raw API/push device dict with a
    "states" list, which is what the regular poll and push paths pass.
    """
    if not isinstance(state_data, dict):
        return None
    states = state_data.get("states")
    if isinstance(states, list):
        value = next(
            (
                item.get("value")
                for item in states
                if isinstance(item, dict)
                and item.get("capability") == LOCK_CAPABILITY
                and item.get("name") == LOCK_ATTRIBUTE
            ),
            None,
        )
        return _lock_value(value)
    cap = state_data.get(LOCK_CAPABILITY)
    if not isinstance(cap, dict) or LOCK_ATTRIBUTE not in cap:
        return None
    return _lock_value(cap[LOCK_ATTRIBUTE])


def _lock_value(value: Any) -> bool | None:
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
    """Per-device confirmation bursts (1, 1, 1, 1, 2, 3, 5, 8, 13s)."""

    def __init__(self, coordinator) -> None:
        self.coordinator = coordinator
        self._bursts: dict[str, dict[str, Any]] = {}
        self._confirmations: dict[str, dict[str, Any]] = {}
        self._ticks: dict[str, Any] = {}
        self.stats = AdaptiveStats()

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
        self.stats.record_end(reason, changed=bool(current.get("changed", True)))
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

        device = self.coordinator.devices.get(device_id)
        before = reported_locked(device.get_state_data()) if device else None
        self._bursts[device_id] = {
            "expected_locked": expected_locked,
            "attempt": 0,
            "delay": initial,
            "failures": 0,
            "unsub": None,
            # For the "caught" warning and stats: when the command (or the
            # re-check) started, and what the API last said before it.
            "started_at": dt_util.utcnow(),
            "rearm": not clear_confirmation,
            "before": before,
        }
        self.stats.record_start(rearm=not clear_confirmation)
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
        reason: str = AA_END_POLL,
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

    def _report_caught(
        self, device_id: str, device, burst: dict[str, Any], locked: bool
    ) -> None:
        """A burst poll, not a push or regular poll, saw the change."""
        polls = int(burst["attempt"])
        started = burst.get("started_at")
        seconds = (
            (dt_util.utcnow() - started).total_seconds() if started else 0.0
        )
        state = "locked" if locked else "unlocked"
        name = getattr(device, "name", None)
        name = name if isinstance(name, str) and name else device_id
        _LOGGER.warning(
            "Adaptive Aggressive caught %s (%s) changing to %s %.1fs after the %s,"
            " on burst poll %s of %s (intervals: %s)",
            name,
            device_id,
            state,
            seconds,
            "re-check started" if burst.get("rearm") else "command",
            polls,
            ADAPTIVE_AGGRESSIVE_MAX_ATTEMPTS,
            "+".join(str(d) for d in confirmation_delays(polls)) + "s",
        )
        self.stats.record_caught(device_id, seconds, polls, state)

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

        # Respect the failure threshold: if regular polls are already failing,
        # a burst only adds load to an API that is struggling.
        failures = getattr(self.coordinator, "consecutive_update_failures", 0)
        if isinstance(failures, int) and failures >= MAX_CONSECUTIVE_UPDATE_FAILURES:
            self.cancel(device_id, "poll failure threshold", burst=burst, notify=True)
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
            burst["failures"] = 0
            self.stats.record_poll(ok=True)
        except ConfigEntryAuthFailed:
            self.stats.record_poll(ok=False)
            if self._bursts.get(device_id) is burst:
                self.cancel(device_id, "auth failed", burst=burst, notify=True)
            return
        except Exception as err:  # noqa: BLE001
            self.stats.record_poll(ok=False)
            _LOGGER.warning(
                "Adaptive aggressive poll failed for %s: %s",
                device_id,
                type(err).__name__,
            )
            if self._bursts.get(device_id) is burst:
                burst["failures"] = int(burst.get("failures", 0)) + 1
                if burst["failures"] >= MAX_CONSECUTIVE_UPDATE_FAILURES:
                    self.cancel(device_id, "api errors", burst=burst, notify=True)
                    return

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
            burst["changed"] = burst.get("before") != expected
            if burst["changed"]:
                self._report_caught(device_id, device, burst, expected)
            self.cancel(device_id, AA_END_CAUGHT, burst=burst)
            return

        if burst["attempt"] >= ADAPTIVE_AGGRESSIVE_MAX_ATTEMPTS:
            self.cancel(device_id, "max attempts", burst=burst, notify=True)
            return

        # Not None: the max-attempts check above ends the burst first.
        upcoming = next_delay(int(burst["attempt"]))
        idle = self.idle_interval_seconds()
        if upcoming >= idle:
            self.cancel(device_id, "idle cap", burst=burst, notify=True)
            return

        burst["delay"] = upcoming
        self._schedule(device_id, upcoming)
