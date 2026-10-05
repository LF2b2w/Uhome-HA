"""Keep the API and Adaptive Aggressive totals across reloads and restarts.

Totals are saved per config entry with Home Assistant's Store helper, under
.storage/u_tec.stats.<entry_id>. Saves are throttled: the first change after
a save schedules one write SAVE_DELAY seconds later, and further changes in
that window ride along with it, so a 1s debug polling session writes at
most once per window. Unload writes immediately, and Home Assistant flushes
a pending write when it shuts down. The rolling "last hour" figures are not
saved.
"""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.storage import Store

from .const import DOMAIN
from .stats import AdaptiveStats, ApiStats

_LOGGER = logging.getLogger(__name__)

STORAGE_VERSION = 1
STORAGE_MINOR_VERSION = 1
SAVE_DELAY = 30  # seconds


def storage_key(entry_id: str) -> str:
    return f"{DOMAIN}.stats.{entry_id}"


class _StatsStorage(Store[dict[str, Any]]):
    """Store whose migration keeps whatever it can read.

    restore() ignores anything it does not recognise, so data written by a
    newer or older layout loads as far as it matches and the rest counts
    from zero.
    """

    async def _async_migrate_func(
        self, old_major_version: int, old_minor_version: int, old_data: Any
    ) -> dict[str, Any]:
        _LOGGER.debug(
            "Migrating U-Tec stats storage from %s.%s",
            old_major_version,
            old_minor_version,
        )
        return old_data if isinstance(old_data, dict) else {}


class StatsStore:
    """Load, throttle-save and flush one config entry's totals."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry_id: str,
        api_stats: ApiStats,
        adaptive_stats: AdaptiveStats,
        *,
        save_delay: float = SAVE_DELAY,
    ) -> None:
        self._store = _StatsStorage(
            hass,
            STORAGE_VERSION,
            storage_key(entry_id),
            minor_version=STORAGE_MINOR_VERSION,
        )
        self._api = api_stats
        self._adaptive = adaptive_stats
        self._save_delay = save_delay
        self._save_pending = False

    async def async_load(self) -> None:
        """Add the saved totals, then start saving on every change."""
        try:
            data = await self._store.async_load()
        except Exception:  # a bad file must not block setup
            _LOGGER.warning(
                "Could not read saved U-Tec counters; counting from zero",
                exc_info=True,
            )
            data = None
        if isinstance(data, dict):
            self._api.restore(data.get("api"))
            self._adaptive.restore(data.get("adaptive"))
        self._api.set_change_listener(self.async_schedule_save)
        self._adaptive.set_change_listener(self.async_schedule_save)

    def data(self) -> dict[str, Any]:
        return {
            "api": self._api.to_storage(),
            "adaptive": self._adaptive.to_storage(),
        }

    @callback
    def _data_for_delayed_save(self) -> dict[str, Any]:
        # Called when the write actually happens, so it carries every change
        # up to that moment; the next change schedules a new write.
        self._save_pending = False
        return self.data()

    @callback
    def async_schedule_save(self) -> None:
        if self._save_pending:
            return
        self._save_pending = True
        self._store.async_delay_save(self._data_for_delayed_save, self._save_delay)

    async def async_save(self) -> None:
        """Write now (unload)."""
        self._save_pending = False
        await self._store.async_save(self.data())

    async def async_shutdown(self) -> None:
        """Final write for this entry; later changes are not saved.

        Detaching first means this instance never schedules another write,
        so after a reload it cannot overwrite what the new instance saves.
        """
        self._api.set_change_listener(None)
        self._adaptive.set_change_listener(None)
        await self.async_save()


async def async_remove_stats(hass: HomeAssistant, entry_id: str) -> None:
    """Delete the saved totals when the config entry is removed."""
    await _StatsStorage(
        hass, STORAGE_VERSION, storage_key(entry_id), minor_version=STORAGE_MINOR_VERSION
    ).async_remove()
