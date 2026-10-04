"""Debug Polling Mode: a short, self-ending burst of 1s polling.

Fast polling is useful while testing the integration, but a permanent 1s
interval on a shared vendor API is a lot of traffic for everyone. This mode
gives testers the fast view for a bounded window instead of a saved setting.

While a session is active:

- the coordinator polls every DEBUG_POLL_INTERVAL seconds;
- Adaptive Aggressive bursts are cancelled and not started;
- push payloads are still accepted and timestamped, but not applied, and they
  do not reset the poll-failure counter;
- optimistic updates are off and any outstanding optimism is dropped;

so the state on screen is raw polled state. The session ends after
DEBUG_POLL_DURATION seconds, when stopped, on unload, or as soon as the
poll-failure threshold trips. Ending it restores the configured interval.
Nothing is written to the config entry, so a restart or reload always comes
back at the normal interval.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from homeassistant.helpers.event import async_call_later
from homeassistant.util import dt as dt_util

from .const import DEBUG_POLL_DURATION, DEBUG_POLL_INTERVAL

_LOGGER = logging.getLogger(__name__)

REASON_EXPIRED = "expired"
REASON_STOPPED = "stopped"
REASON_FAILURES = "failure threshold reached"
REASON_UNLOAD = "unload"


def debug_polling_active(coordinator: Any) -> bool:
    """Return True only when a real coordinator reports an active session.

    Entities call this instead of reading the attribute directly so a stub
    coordinator (MagicMock in entity tests) never reads as active.
    """
    return getattr(coordinator, "debug_polling_active", False) is True


class DebugPolling:
    """Owns one Debug Polling Mode session for a coordinator."""

    def __init__(self, coordinator) -> None:
        self.coordinator = coordinator
        self.active = False
        self.started_at: datetime | None = None
        self.ends_at: datetime | None = None
        self.requests = 0
        self.last_session: dict[str, Any] | None = None
        self._restore_interval: timedelta | None = None
        self._unsub_expire = None

    def _reschedule(self) -> None:
        # Same pattern async_update_options uses: _schedule_refresh is a
        # private HA API, so guard the call.
        schedule = getattr(self.coordinator, "_schedule_refresh", None)
        if callable(schedule):
            schedule()

    @property
    def restore_interval(self) -> timedelta | None:
        """The interval that comes back when the session ends."""
        return self._restore_interval

    def set_restore_interval(self, interval: timedelta) -> None:
        """Record a new configured interval while a session is active.

        Options saves (and token refreshes, which fire the same listener)
        must not cut the session short or be lost; the new value is applied
        when the session ends.
        """
        self._restore_interval = interval

    def start(self) -> bool:
        """Start a session. Returns False if one is already running.

        A press while active does not extend or restart the session, so the
        window can never grow past DEBUG_POLL_DURATION.
        """
        if self.active:
            _LOGGER.info(
                "U-Tec debug polling already active until %s; not extended",
                self.ends_at,
            )
            return False

        now = dt_util.utcnow()
        self.active = True
        self.started_at = now
        self.ends_at = now + timedelta(seconds=DEBUG_POLL_DURATION)
        self.requests = 0
        self._restore_interval = self.coordinator.update_interval

        # Raw polled state only: no confirmation bursts during the session.
        self.coordinator.adaptive.cancel_all("debug polling")

        self.coordinator.update_interval = timedelta(seconds=DEBUG_POLL_INTERVAL)
        self._reschedule()
        self._unsub_expire = async_call_later(
            self.coordinator.hass, DEBUG_POLL_DURATION, self._async_expire
        )
        _LOGGER.warning(
            "U-Tec debug polling started: polling every %ss for %ss (until %s). "
            "Adaptive Aggressive, push state and optimistic updates are paused",
            DEBUG_POLL_INTERVAL,
            DEBUG_POLL_DURATION,
            self.ends_at,
        )
        # Lets entities drop optimistic state and diagnostics show the session.
        self.coordinator.async_update_listeners()
        return True

    async def _async_expire(self, _now) -> None:
        self._unsub_expire = None
        self.stop(REASON_EXPIRED)

    def check_expired(self) -> None:
        """Second guard on the hard limit, called before every poll."""
        if self.active and self.ends_at and dt_util.utcnow() >= self.ends_at:
            self.stop(REASON_EXPIRED)

    def count_request(self) -> None:
        if self.active:
            self.requests += 1

    def stop(self, reason: str = REASON_STOPPED) -> bool:
        """End the session and restore the configured interval."""
        if not self.active:
            return False
        if self._unsub_expire:
            self._unsub_expire()
            self._unsub_expire = None

        ended_at = dt_util.utcnow()
        self.active = False
        if self._restore_interval is not None:
            self.coordinator.update_interval = self._restore_interval
        self.last_session = {
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "ended_at": ended_at.isoformat(),
            "requests": self.requests,
            "reason": reason,
        }
        _LOGGER.warning(
            "U-Tec debug polling stopped (%s) after %d request(s); "
            "polling every %ss again",
            reason,
            self.requests,
            int(self.coordinator.update_interval.total_seconds()),
        )
        self.started_at = None
        self.ends_at = None
        self._restore_interval = None

        if reason != REASON_UNLOAD:
            self._reschedule()
            self.coordinator.async_update_listeners()
        return True

    def shutdown(self) -> None:
        """Unload hook: end any session without touching entities."""
        self.stop(REASON_UNLOAD)

    def as_dict(self) -> dict[str, Any]:
        """Diagnostics summary."""
        return {
            "active": self.active,
            "ends_at": self.ends_at.isoformat() if self.ends_at else None,
            "requests_this_session": self.requests if self.active else None,
            "last_session": self.last_session,
        }
