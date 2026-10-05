"""Accounting of what this install asks of the U-Tec API.

Every request this integration makes goes through MeteredApi, which counts it
by kind (discovery, state query, command, other), times it, and notes
failures, including U-Tec's HTTP-200 error envelopes. The coordinator records
push deliveries. Diagnostic sensors on the "U-Tec Integration" device and the
diagnostics download read from ApiStats.

Totals are saved per config entry by stats_store.StatsStore, so they carry
across reloads and Home Assistant restarts. Each record method calls the
_on_change hook, which StatsStore uses to schedule a throttled save. The
rolling "last hour" window is kept in memory only and starts empty after a
reload or restart.
"""

from __future__ import annotations

import logging
import time
from collections import deque
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any, ClassVar

from homeassistant.util import dt as dt_util

_LOGGER = logging.getLogger(__name__)

KIND_DISCOVERY = "discovery"
KIND_QUERY = "query"
KIND_COMMAND = "command"
KIND_OTHER = "other"
KINDS = (KIND_DISCOVERY, KIND_QUERY, KIND_COMMAND, KIND_OTHER)

ROLLING_WINDOW = timedelta(hours=1)

# Commands the integration chose not to send, by reason.
SKIP_PASSAGE_MODE = "passage_mode"


def _count(value: Any) -> int:
    """A stored counter, or 0 if it is missing or not a non-negative int."""
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return 0
    return value


def _number(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
        return 0.0
    return float(value)


def _when(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    parsed = dt_util.parse_datetime(value)
    if parsed is None:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt_util.UTC)
    return parsed


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _count_map(value: Any) -> dict[str, int]:
    if not isinstance(value, dict):
        return {}
    return {str(k): _count(v) for k, v in value.items() if _count(v)}


def _add_counts(target: dict[str, int], stored: Any) -> None:
    for key, count in _count_map(stored).items():
        target[key] = target.get(key, 0) + count


class _Persisted:
    """Change hook shared by the stats classes; StatsStore sets it."""

    _on_change: Callable[[], None] | None = None

    def set_change_listener(self, listener: Callable[[], None] | None) -> None:
        self._on_change = listener

    def _changed(self) -> None:
        if self._on_change is not None:
            self._on_change()


def _is_error_envelope(response: Any) -> bool:
    """U-Tec answers HTTP 200 with payload.error on failure."""
    if not isinstance(response, dict):
        return False
    payload = response.get("payload")
    return isinstance(payload, dict) and isinstance(payload.get("error"), dict)


def _device_ids(method: str, args: tuple, kwargs: dict) -> list[str]:
    """Device ids a request is about, where the call names them."""
    if method == "get_device_state":
        ids = args[0] if args else kwargs.get("device_ids")
        return [str(i) for i in ids] if isinstance(ids, (list, tuple)) else []
    if method in ("query_device", "send_command"):
        device_id = args[0] if args else kwargs.get("device_id")
        return [str(device_id)] if device_id else []
    return []


class ApiStats(_Persisted):
    """Counters for one config entry's API usage and push deliveries."""

    def __init__(self) -> None:
        self.counting_since: datetime = dt_util.utcnow()
        self.requests: dict[str, int] = dict.fromkeys(KINDS, 0)
        self.failures = 0
        self.last_latency_ms: float | None = None
        self.last_response_at: datetime | None = None
        self.last_failure_at: datetime | None = None
        self.pushes_received = 0
        self.pushes_applied = 0
        self.pushes_ignored = 0
        # device_id -> {"query": n, "command": n}
        self.per_device: dict[str, dict[str, int]] = {}
        # reason -> count, and device_id -> count, of commands not sent
        self.commands_skipped: dict[str, int] = {}
        self.skipped_per_device: dict[str, int] = {}
        self._recent: deque[datetime] = deque()

    @property
    def total_requests(self) -> int:
        return sum(self.requests.values())

    def record(
        self,
        kind: str,
        *,
        ok: bool,
        latency_s: float | None,
        device_ids: list[str] | None = None,
    ) -> None:
        now = dt_util.utcnow()
        self.requests[kind] = self.requests.get(kind, 0) + 1
        self._recent.append(now)
        self._prune(now)
        self.last_response_at = now
        if latency_s is not None:
            self.last_latency_ms = round(latency_s * 1000, 1)
        if not ok:
            self.failures += 1
            self.last_failure_at = now
        if kind in (KIND_QUERY, KIND_COMMAND):
            for device_id in device_ids or ():
                counts = self.per_device.setdefault(
                    device_id, {KIND_QUERY: 0, KIND_COMMAND: 0}
                )
                counts[kind] += 1
        self._changed()

    def record_push_received(self) -> None:
        self.pushes_received += 1
        self._changed()

    def record_push_outcome(self, *, applied: bool) -> None:
        if applied:
            self.pushes_applied += 1
        else:
            self.pushes_ignored += 1
        self._changed()

    def _prune(self, now: datetime) -> None:
        cutoff = now - ROLLING_WINDOW
        while self._recent and self._recent[0] <= cutoff:
            self._recent.popleft()

    def requests_last_hour(self) -> int:
        self._prune(dt_util.utcnow())
        return len(self._recent)

    def requests_per_device_last_hour(self, device_count: int) -> float | None:
        if device_count <= 0:
            return None
        return round(self.requests_last_hour() / device_count, 1)

    def record_command_skipped(self, reason: str, device_id: str) -> None:
        """A command the integration did not send because it would be a no-op."""
        self.commands_skipped[reason] = self.commands_skipped.get(reason, 0) + 1
        self.skipped_per_device[device_id] = self.skipped_per_device.get(device_id, 0) + 1
        self._changed()

    def device_commands(self, device_id: str) -> int:
        return self.per_device.get(device_id, {}).get(KIND_COMMAND, 0)

    def as_dict(self, device_count: int = 0) -> dict[str, Any]:
        """Diagnostics summary."""
        return {
            "counting_since": self.counting_since.isoformat(),
            "total_requests": self.total_requests,
            "requests_by_kind": dict(self.requests),
            "failures": self.failures,
            "requests_last_hour": self.requests_last_hour(),
            "requests_per_device_last_hour": self.requests_per_device_last_hour(
                device_count
            ),
            "last_latency_ms": self.last_latency_ms,
            "last_response_at": (
                self.last_response_at.isoformat() if self.last_response_at else None
            ),
            "last_failure_at": (
                self.last_failure_at.isoformat() if self.last_failure_at else None
            ),
            "pushes": {
                "received": self.pushes_received,
                "applied": self.pushes_applied,
                "ignored": self.pushes_ignored,
            },
            "per_device": {k: dict(v) for k, v in self.per_device.items()},
            "commands_skipped": dict(self.commands_skipped),
            "commands_skipped_per_device": dict(self.skipped_per_device),
        }

    def to_storage(self) -> dict[str, Any]:
        """Totals worth keeping across restarts (not the rolling window)."""
        return {
            "counting_since": self.counting_since.isoformat(),
            "requests": dict(self.requests),
            "failures": self.failures,
            "last_latency_ms": self.last_latency_ms,
            "last_response_at": _iso(self.last_response_at),
            "last_failure_at": _iso(self.last_failure_at),
            "pushes": {
                "received": self.pushes_received,
                "applied": self.pushes_applied,
                "ignored": self.pushes_ignored,
            },
            "per_device": {k: dict(v) for k, v in self.per_device.items()},
            "commands_skipped": dict(self.commands_skipped),
            "skipped_per_device": dict(self.skipped_per_device),
        }

    def restore(self, data: Any) -> None:
        """Add saved totals to this (normally fresh) instance.

        Adding rather than replacing means nothing counted before the load
        is lost. Missing or malformed fields count as zero.
        """
        if not isinstance(data, dict):
            return
        if (since := _when(data.get("counting_since"))) is not None:
            self.counting_since = min(since, self.counting_since)
        _add_counts(self.requests, data.get("requests"))
        self.failures += _count(data.get("failures"))
        if self.last_latency_ms is None and _number(data.get("last_latency_ms")):
            self.last_latency_ms = round(_number(data["last_latency_ms"]), 1)
        if self.last_response_at is None:
            self.last_response_at = _when(data.get("last_response_at"))
        if self.last_failure_at is None:
            self.last_failure_at = _when(data.get("last_failure_at"))
        pushes = data.get("pushes")
        if isinstance(pushes, dict):
            self.pushes_received += _count(pushes.get("received"))
            self.pushes_applied += _count(pushes.get("applied"))
            self.pushes_ignored += _count(pushes.get("ignored"))
        per_device = data.get("per_device")
        if isinstance(per_device, dict):
            for device_id, stored in per_device.items():
                if not isinstance(stored, dict):
                    continue
                counts = self.per_device.setdefault(
                    str(device_id), {KIND_QUERY: 0, KIND_COMMAND: 0}
                )
                for kind in (KIND_QUERY, KIND_COMMAND):
                    counts[kind] += _count(stored.get(kind))
        _add_counts(self.commands_skipped, data.get("commands_skipped"))
        _add_counts(self.skipped_per_device, data.get("skipped_per_device"))


class MeteredApi:
    """Wrap a UHomeApi so every request is counted in ApiStats.

    Only the request methods are metered; everything else passes through
    untouched. Internal calls inside the client (its own request helpers)
    are not seen here, so nothing is double counted.
    """

    _KINDS: ClassVar[dict[str, str]] = {
        "discover_devices": KIND_DISCOVERY,
        "get_device_state": KIND_QUERY,
        "query_device": KIND_QUERY,
        "send_command": KIND_COMMAND,
        "set_push_status": KIND_OTHER,
        "validate_auth": KIND_OTHER,
    }

    def __init__(self, api: Any, stats: ApiStats) -> None:
        self._api = api
        self.stats = stats

    @property
    def wrapped(self) -> Any:
        return self._api

    def __getattr__(self, name: str) -> Any:
        attr = getattr(self._api, name)
        kind = self._KINDS.get(name)
        if kind is None or not callable(attr):
            return attr

        async def _metered(*args, **kwargs):
            devices = _device_ids(name, args, kwargs)
            start = time.perf_counter()
            try:
                result = await attr(*args, **kwargs)
            except Exception:
                self.stats.record(
                    kind,
                    ok=False,
                    latency_s=time.perf_counter() - start,
                    device_ids=devices,
                )
                raise
            self.stats.record(
                kind,
                ok=not _is_error_envelope(result),
                latency_s=time.perf_counter() - start,
                device_ids=devices,
            )
            return result

        return _metered


# How an Adaptive Aggressive burst ended, grouped for the AA sensors.
AA_END_CAUGHT = "confirmed"  # a burst poll saw the commanded state
AA_END_POLL = "poll"  # a regular poll saw it first
AA_END_PUSH = "push"  # a push carrying st.lock saw it first
AA_FAILURE_REASONS = frozenset({"api errors", "poll failure threshold", "auth failed"})
AA_EXHAUSTED_REASONS = frozenset({"max attempts", "idle cap"})


class AdaptiveStats(_Persisted):
    """Counters for Adaptive Aggressive confirmation bursts.

    One burst ends exactly once, so the outcome counters add up to
    bursts_started minus any burst still running. Averages cover only
    bursts where a burst poll caught a real state change. Saved with the
    API totals by StatsStore.
    """

    _COUNTERS = (
        "bursts_started",
        "rearms",
        "polls",
        "poll_failures",
        "changes_caught",
        "confirmed_without_change",
        "ended_by_poll",
        "ended_by_push",
        "ended_by_failures",
        "exhausted",
        "cancelled",
    )

    def __init__(self) -> None:
        self.counting_since: datetime = dt_util.utcnow()
        self.bursts_started = 0
        self.rearms = 0
        self.polls = 0
        self.poll_failures = 0
        self.changes_caught = 0
        self.confirmed_without_change = 0
        self.ended_by_poll = 0
        self.ended_by_push = 0
        self.ended_by_failures = 0
        self.exhausted = 0
        self.cancelled = 0
        self.last_caught: dict[str, Any] | None = None
        self._caught_seconds_total = 0.0
        self._caught_polls_total = 0

    def record_start(self, *, rearm: bool) -> None:
        self.bursts_started += 1
        if rearm:
            self.rearms += 1
        self._changed()

    def record_poll(self, *, ok: bool) -> None:
        self.polls += 1
        if not ok:
            self.poll_failures += 1
        self._changed()

    def record_caught(
        self, device_id: str, seconds: float, polls: int, state: str
    ) -> None:
        self.changes_caught += 1
        self._caught_seconds_total += seconds
        self._caught_polls_total += polls
        self.last_caught = {
            "device_id": device_id,
            "state": state,
            "seconds": round(seconds, 1),
            "polls": polls,
            "at": dt_util.utcnow().isoformat(),
        }
        self._changed()

    def record_end(self, reason: str, *, changed: bool = True) -> None:
        if reason == AA_END_CAUGHT:
            if not changed:
                self.confirmed_without_change += 1
        elif reason == AA_END_POLL:
            self.ended_by_poll += 1
        elif reason == AA_END_PUSH:
            self.ended_by_push += 1
        elif reason in AA_FAILURE_REASONS:
            self.ended_by_failures += 1
        elif reason in AA_EXHAUSTED_REASONS:
            self.exhausted += 1
        else:
            # restarted, debug polling, unload, device gone
            self.cancelled += 1
        self._changed()

    @property
    def avg_seconds_to_detect(self) -> float | None:
        if not self.changes_caught:
            return None
        return round(self._caught_seconds_total / self.changes_caught, 1)

    @property
    def avg_polls_to_detect(self) -> float | None:
        if not self.changes_caught:
            return None
        return round(self._caught_polls_total / self.changes_caught, 1)

    def as_dict(self) -> dict[str, Any]:
        """Diagnostics summary."""
        return {
            "counting_since": self.counting_since.isoformat(),
            "bursts_started": self.bursts_started,
            "rearms": self.rearms,
            "polls": self.polls,
            "poll_failures": self.poll_failures,
            "changes_caught": self.changes_caught,
            "avg_seconds_to_detect": self.avg_seconds_to_detect,
            "avg_polls_to_detect": self.avg_polls_to_detect,
            "ended": {
                "caught_by_burst": self.changes_caught,
                "confirmed_without_change": self.confirmed_without_change,
                "regular_poll": self.ended_by_poll,
                "push": self.ended_by_push,
                "failures": self.ended_by_failures,
                "schedule_exhausted": self.exhausted,
                "cancelled": self.cancelled,
            },
            "last_caught": self.last_caught,
        }

    def to_storage(self) -> dict[str, Any]:
        """Totals plus the sums behind the averages."""
        data: dict[str, Any] = {
            "counting_since": self.counting_since.isoformat(),
            "caught_seconds_total": round(self._caught_seconds_total, 3),
            "caught_polls_total": self._caught_polls_total,
            "last_caught": self.last_caught,
        }
        for name in self._COUNTERS:
            data[name] = getattr(self, name)
        return data

    def restore(self, data: Any) -> None:
        """Add saved totals to this (normally fresh) instance."""
        if not isinstance(data, dict):
            return
        if (since := _when(data.get("counting_since"))) is not None:
            self.counting_since = min(since, self.counting_since)
        for name in self._COUNTERS:
            setattr(self, name, getattr(self, name) + _count(data.get(name)))
        self._caught_seconds_total += _number(data.get("caught_seconds_total"))
        self._caught_polls_total += _count(data.get("caught_polls_total"))
        if self.last_caught is None and isinstance(data.get("last_caught"), dict):
            self.last_caught = dict(data["last_caught"])
