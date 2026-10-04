"""In-memory accounting of what this install asks of the U-Tec API.

Every request this integration makes goes through MeteredApi, which counts it
by kind (discovery, state query, command, other), times it, and notes
failures, including U-Tec's HTTP-200 error envelopes. The coordinator records
push deliveries. Diagnostic sensors on the "U-Tec Integration" device and the
diagnostics download read from ApiStats.

Counters live in memory only and start from zero on every restart or reload.
The totals use state_class TOTAL_INCREASING, so Home Assistant statistics
treat that as a meter reset rather than a drop.
"""

from __future__ import annotations

import logging
import time
from collections import deque
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


class ApiStats:
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
        }


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
