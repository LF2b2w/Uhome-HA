"""Saved counters: load, throttled save, migrate, and survive reloads."""

from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.u_tec.const import CONF_PUSH_ENABLED, DOMAIN
from custom_components.u_tec.stats import (
    AA_END_PUSH,
    KIND_COMMAND,
    KIND_DISCOVERY,
    KIND_QUERY,
    SKIP_PASSAGE_MODE,
    AdaptiveStats,
    ApiStats,
)
from custom_components.u_tec.stats_store import (
    STORAGE_VERSION,
    StatsStore,
    storage_key,
)
from tests.common import make_config_entry

ENTRY = "entry-1"
KEY = storage_key(ENTRY)


def _busy_stats() -> tuple[ApiStats, AdaptiveStats]:
    api, aa = ApiStats(), AdaptiveStats()
    api.record(KIND_DISCOVERY, ok=True, latency_s=0.2)
    api.record(KIND_QUERY, ok=True, latency_s=0.1, device_ids=["lock-1"])
    api.record(KIND_COMMAND, ok=False, latency_s=0.3, device_ids=["lock-1"])
    api.record_push_received()
    api.record_push_outcome(applied=True)
    api.record_command_skipped(SKIP_PASSAGE_MODE, "lock-1")
    aa.record_start(rearm=False)
    aa.record_start(rearm=True)
    aa.record_poll(ok=True)
    aa.record_poll(ok=False)
    aa.record_caught("lock-1", 4.0, 3, "locked")
    aa.record_caught("lock-1", 2.0, 1, "unlocked")
    aa.record_end(AA_END_PUSH)
    return api, aa


async def test_load_from_empty_storage_starts_at_zero(hass, hass_storage):
    api, aa = ApiStats(), AdaptiveStats()
    since = api.counting_since
    await StatsStore(hass, ENTRY, api, aa).async_load()

    assert api.total_requests == 0
    assert api.failures == api.pushes_received == 0
    assert api.commands_skipped == {} and api.per_device == {}
    assert aa.bursts_started == aa.polls == aa.changes_caught == 0
    assert aa.avg_seconds_to_detect is None
    assert api.counting_since == since
    assert KEY not in hass_storage  # nothing written until something changes


async def test_round_trip_restores_every_total(hass, hass_storage):
    api, aa = _busy_stats()
    store = StatsStore(hass, ENTRY, api, aa)
    await store.async_save()

    saved = hass_storage[KEY]
    assert saved["version"] == STORAGE_VERSION
    assert saved["data"]["api"]["requests"][KIND_COMMAND] == 1

    api2, aa2 = ApiStats(), AdaptiveStats()
    await StatsStore(hass, ENTRY, api2, aa2).async_load()

    assert api2.requests == api.requests
    assert api2.failures == 1
    assert (api2.pushes_received, api2.pushes_applied, api2.pushes_ignored) == (1, 1, 0)
    assert api2.per_device == {"lock-1": {KIND_QUERY: 1, KIND_COMMAND: 1}}
    assert api2.commands_skipped == {SKIP_PASSAGE_MODE: 1}
    assert api2.skipped_per_device == {"lock-1": 1}
    assert api2.last_latency_ms == api.last_latency_ms
    assert api2.last_failure_at == api.last_failure_at
    assert api2.counting_since == api.counting_since
    # The rolling window is not saved.
    assert api2.requests_last_hour() == 0

    assert aa2.as_dict() == aa.as_dict()
    assert aa2.avg_seconds_to_detect == 3.0
    assert aa2.avg_polls_to_detect == 2.0


async def test_restore_adds_to_counts_made_before_load(hass, hass_storage):
    old_api, old_aa = _busy_stats()
    await StatsStore(hass, ENTRY, old_api, old_aa).async_save()

    api, aa = ApiStats(), AdaptiveStats()
    api.record(KIND_DISCOVERY, ok=True, latency_s=0.1)
    aa.record_poll(ok=True)
    await StatsStore(hass, ENTRY, api, aa).async_load()

    assert api.requests[KIND_DISCOVERY] == 2
    assert aa.polls == 3


async def test_malformed_values_count_as_zero(hass, hass_storage):
    hass_storage[KEY] = {
        "version": STORAGE_VERSION,
        "minor_version": 1,
        "key": KEY,
        "data": {
            "api": {
                "counting_since": "not a date",
                "requests": {KIND_QUERY: "7", KIND_COMMAND: -3, KIND_DISCOVERY: 4},
                "failures": True,
                "pushes": ["nope"],
                "per_device": {"lock-1": "x", "lock-2": {KIND_COMMAND: 2}},
                "commands_skipped": None,
                "unknown_future_field": 1,
            },
            "adaptive": {"polls": 5, "bursts_started": "9", "last_caught": "x"},
        },
    }
    api, aa = ApiStats(), AdaptiveStats()
    await StatsStore(hass, ENTRY, api, aa).async_load()

    assert api.requests[KIND_QUERY] == 0
    assert api.requests[KIND_COMMAND] == 0
    assert api.requests[KIND_DISCOVERY] == 4
    assert api.failures == 0 and api.pushes_received == 0
    assert api.per_device == {"lock-2": {KIND_QUERY: 0, KIND_COMMAND: 2}}
    assert api.commands_skipped == {}
    assert aa.polls == 5 and aa.bursts_started == 0 and aa.last_caught is None


async def test_non_dict_payload_loads_as_empty(hass, hass_storage):
    hass_storage[KEY] = {"version": STORAGE_VERSION, "minor_version": 1, "key": KEY, "data": "junk"}
    api, aa = ApiStats(), AdaptiveStats()
    await StatsStore(hass, ENTRY, api, aa).async_load()
    assert api.total_requests == 0 and aa.polls == 0


async def test_unreadable_storage_does_not_block_setup(hass, hass_storage):
    api, aa = ApiStats(), AdaptiveStats()
    store = StatsStore(hass, ENTRY, api, aa)
    with patch.object(store._store, "async_load", side_effect=ValueError("bad json")):
        await store.async_load()
    assert api.total_requests == 0
    # Still saves afterwards.
    api.record(KIND_QUERY, ok=True, latency_s=0.1)
    await store.async_save()
    assert hass_storage[KEY]["data"]["api"]["requests"][KIND_QUERY] == 1


async def test_migrates_older_storage_version(hass, hass_storage):
    hass_storage[KEY] = {
        "version": 0,
        "minor_version": 1,
        "key": KEY,
        "data": {"api": {"requests": {KIND_COMMAND: 6}}, "adaptive": {"bursts_started": 2}},
    }
    api, aa = ApiStats(), AdaptiveStats()
    await StatsStore(hass, ENTRY, api, aa).async_load()
    assert api.requests[KIND_COMMAND] == 6
    assert aa.bursts_started == 2


async def test_changes_are_saved_once_per_window(hass, hass_storage):
    api, aa = ApiStats(), AdaptiveStats()
    store = StatsStore(hass, ENTRY, api, aa, save_delay=30)
    await store.async_load()

    with patch.object(store, "data", wraps=store.data) as data:
        for _ in range(50):
            api.record(KIND_QUERY, ok=True, latency_s=0.1)
        aa.record_poll(ok=True)
        await hass.async_block_till_done()
        assert KEY not in hass_storage

        async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=31))
        await hass.async_block_till_done()
        assert data.call_count == 1

    saved = hass_storage[KEY]["data"]
    assert saved["api"]["requests"][KIND_QUERY] == 50
    assert saved["adaptive"]["polls"] == 1

    # The next change schedules a new write.
    api.record(KIND_COMMAND, ok=True, latency_s=0.1)
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=62))
    await hass.async_block_till_done()
    assert hass_storage[KEY]["data"]["api"]["requests"][KIND_COMMAND] == 1


async def test_shutdown_writes_and_detaches(hass, hass_storage):
    api, aa = ApiStats(), AdaptiveStats()
    store = StatsStore(hass, ENTRY, api, aa)
    await store.async_load()
    api.record(KIND_QUERY, ok=True, latency_s=0.1)
    await store.async_shutdown()
    assert hass_storage[KEY]["data"]["api"]["requests"][KIND_QUERY] == 1

    api.record(KIND_QUERY, ok=True, latency_s=0.1)
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=120))
    await hass.async_block_till_done()
    assert hass_storage[KEY]["data"]["api"]["requests"][KIND_QUERY] == 1


async def _setup_entry(hass, entry):
    instance = MagicMock()
    instance.discover_devices = AsyncMock(return_value={"payload": {"devices": []}})
    instance.get_device_state = AsyncMock(return_value={"payload": {"devices": []}})
    instance.set_push_status = AsyncMock(return_value={})
    with patch("custom_components.u_tec.UHomeApi", return_value=instance), patch(
        "custom_components.u_tec.config_entry_oauth2_flow.async_get_config_entry_implementation"
    ), patch("custom_components.u_tec.config_entry_oauth2_flow.OAuth2Session"), patch(
        "custom_components.u_tec.aiohttp_client.async_get_clientsession",
        return_value=MagicMock(),
    ), patch(
        "custom_components.u_tec.coordinator.UhomeDataUpdateCoordinator.async_start_periodic_discovery",
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    return hass.data[DOMAIN][entry.entry_id]["coordinator"]


async def test_counters_survive_reload_and_entry_removal_deletes_them(
    hass, hass_storage
):
    entry = make_config_entry(entry_id=ENTRY, options={CONF_PUSH_ENABLED: False})
    entry.add_to_hass(hass)

    coordinator = await _setup_entry(hass, entry)
    assert coordinator.stats.requests[KIND_DISCOVERY] == 1
    coordinator.stats.record_command_skipped(SKIP_PASSAGE_MODE, "lock-1")
    coordinator.adaptive.stats.record_start(rearm=False)
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert hass_storage[KEY]["data"]["api"]["requests"][KIND_DISCOVERY] == 1

    coordinator = await _setup_entry(hass, entry)
    assert coordinator.stats.requests[KIND_DISCOVERY] == 2
    assert coordinator.stats.commands_skipped == {SKIP_PASSAGE_MODE: 1}
    assert coordinator.adaptive.stats.bursts_started == 1
    registry = er.async_get(hass)
    sensor_id = registry.async_get_entity_id(
        "sensor", DOMAIN, f"{DOMAIN}_api_requests_{entry.entry_id}"
    )
    assert sensor_id is not None
    coordinator.async_set_updated_data(coordinator.data)
    await hass.async_block_till_done()
    assert int(hass.states.get(sensor_id).state) == coordinator.stats.total_requests >= 2

    assert await hass.config_entries.async_remove(entry.entry_id)
    await hass.async_block_till_done()
    assert KEY not in hass_storage
