"""API accounting: MeteredApi, ApiStats, push counters, and the sensors."""

from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.helpers import entity_registry as er
from utec_client.exceptions import ApiError

from custom_components.u_tec.const import CONF_PUSH_ENABLED, DOMAIN
from custom_components.u_tec.coordinator import UhomeDataUpdateCoordinator
from custom_components.u_tec.sensor import (
    API_STAT_SENSORS,
    UhomeApiStatSensor,
    UhomeDeviceCommandsSensor,
)
from custom_components.u_tec.stats import (
    KIND_COMMAND,
    KIND_DISCOVERY,
    KIND_OTHER,
    KIND_QUERY,
    ApiStats,
    MeteredApi,
)
from tests.common import make_config_entry, make_fake_lock, make_fake_switch

OK = {"payload": {"devices": []}}


@pytest.fixture
def metered(mock_uhome_api):
    stats = ApiStats()
    return MeteredApi(mock_uhome_api, stats), stats


async def test_counts_each_kind(metered):
    api, stats = metered
    await api.discover_devices()
    await api.get_device_state(["lock-1", "sw-1"], None)
    await api.query_device("lock-1")
    await api.send_command("lock-1", "st.lock", "lock", None)
    await api.set_push_status("https://example", "secret")

    assert stats.requests == {
        KIND_DISCOVERY: 1,
        KIND_QUERY: 2,
        KIND_COMMAND: 1,
        KIND_OTHER: 1,
    }
    assert stats.total_requests == 5
    assert stats.failures == 0
    assert stats.last_response_at is not None
    assert stats.last_latency_ms is not None and stats.last_latency_ms >= 0
    assert stats.per_device["lock-1"] == {KIND_QUERY: 2, KIND_COMMAND: 1}
    assert stats.per_device["sw-1"] == {KIND_QUERY: 1, KIND_COMMAND: 0}
    assert stats.device_commands("lock-1") == 1
    assert stats.device_commands("nope") == 0


async def test_returns_result_and_passes_other_attributes(metered, mock_uhome_api):
    api, _ = metered
    mock_uhome_api.get_device_state.return_value = {"payload": {"devices": [{"id": "x"}]}}
    assert await api.get_device_state(["x"], None) == {"payload": {"devices": [{"id": "x"}]}}
    mock_uhome_api.some_value = 42
    assert api.some_value == 42
    assert api.wrapped is mock_uhome_api


async def test_exception_counts_as_failure_and_reraises(metered, mock_uhome_api):
    api, stats = metered
    mock_uhome_api.get_device_state.side_effect = ApiError(500, "boom")
    with pytest.raises(ApiError):
        await api.get_device_state(["lock-1"], None)
    assert stats.requests[KIND_QUERY] == 1
    assert stats.failures == 1
    assert stats.last_failure_at is not None


async def test_http_200_error_envelope_counts_as_failure(metered, mock_uhome_api):
    api, stats = metered
    mock_uhome_api.get_device_state.return_value = {
        "payload": {"error": {"code": "INVALID_TOKEN", "message": "x"}}
    }
    await api.get_device_state(["lock-1"], None)
    assert stats.failures == 1


async def test_rolling_hour_and_per_device(metered, freezer):
    api, stats = metered
    for _ in range(6):
        await api.get_device_state(["a"], None)
    assert stats.requests_last_hour() == 6
    assert stats.requests_per_device_last_hour(3) == 2.0
    assert stats.requests_per_device_last_hour(0) is None

    freezer.tick(timedelta(minutes=59))
    await api.get_device_state(["a"], None)
    assert stats.requests_last_hour() == 7

    freezer.tick(timedelta(minutes=2))
    assert stats.requests_last_hour() == 1
    assert stats.total_requests == 7  # totals never roll off


async def test_as_dict_shape(metered):
    api, stats = metered
    await api.send_command("lock-1", "st.lock", "lock", None)
    stats.pushes_received = 2
    data = stats.as_dict(device_count=1)
    assert data["total_requests"] == 1
    assert data["requests_by_kind"][KIND_COMMAND] == 1
    assert data["requests_per_device_last_hour"] == 1.0
    assert data["pushes"] == {"received": 2, "applied": 0, "ignored": 0}
    assert data["per_device"]["lock-1"][KIND_COMMAND] == 1
    assert data["counting_since"]


@pytest.fixture
async def coordinator(hass, mock_uhome_api):
    entry = make_config_entry()
    entry.add_to_hass(hass)
    coord = UhomeDataUpdateCoordinator(
        hass, mock_uhome_api, config_entry=entry, scan_interval=30, discovery_interval=300,
    )
    yield coord
    coord.debug.shutdown()
    await coord.async_shutdown()


async def test_push_accounting(coordinator):
    sw = make_fake_switch("sw-1")
    coordinator.devices["sw-1"] = sw
    stats = coordinator.stats

    await coordinator.update_push_data([{"id": "sw-1", "states": []}])
    assert (stats.pushes_received, stats.pushes_applied, stats.pushes_ignored) == (1, 1, 0)

    await coordinator.update_push_data({"payload": {"devices": []}})  # empty keepalive
    assert (stats.pushes_received, stats.pushes_applied, stats.pushes_ignored) == (2, 1, 1)

    coordinator.push_devices = ["other"]  # filtered out by push selection
    await coordinator.update_push_data([{"id": "sw-1", "states": []}])
    assert (stats.pushes_received, stats.pushes_applied, stats.pushes_ignored) == (3, 1, 2)

    coordinator.push_devices = []
    coordinator.debug.start()
    await coordinator.update_push_data([{"id": "sw-1", "states": []}])
    assert (stats.pushes_received, stats.pushes_applied, stats.pushes_ignored) == (4, 1, 3)


async def test_push_processing_error_counts_as_ignored(coordinator):
    sw = make_fake_switch("sw-1")
    sw.update_state_data = AsyncMock(side_effect=TypeError("bad"))
    coordinator.devices["sw-1"] = sw
    await coordinator.update_push_data([{"id": "sw-1", "states": []}])
    assert coordinator.stats.pushes_ignored == 1


async def test_sensors_read_stats(coordinator):
    coordinator.devices["lock-1"] = make_fake_lock("lock-1")
    stats = coordinator.stats
    stats.record(KIND_QUERY, ok=True, latency_s=0.25, device_ids=["lock-1"])
    stats.record(KIND_COMMAND, ok=False, latency_s=0.5, device_ids=["lock-1"])
    stats.record(KIND_DISCOVERY, ok=True, latency_s=None)

    sensors = {d.key: UhomeApiStatSensor(coordinator, d) for d in API_STAT_SENSORS}
    values = {key: s.native_value for key, s in sensors.items()}
    assert values["api_requests"] == 3
    assert values["api_requests_last_hour"] == 3
    assert values["api_requests_per_device_last_hour"] == 3.0
    assert values["api_queries"] == 1
    assert values["api_commands"] == 1
    assert values["api_discoveries"] == 1
    assert values["api_failures"] == 1
    assert values["api_last_latency"] == 500.0
    assert values["api_last_response"] == stats.last_response_at
    assert values["pushes_received"] == 0
    assert all(s.available for s in sensors.values())
    entry_id = coordinator.config_entry.entry_id
    assert sensors["api_requests"].unique_id == f"{DOMAIN}_api_requests_{entry_id}"

    per_device = UhomeDeviceCommandsSensor(coordinator, "lock-1")
    assert per_device.native_value == 1
    assert per_device.available is True
    assert per_device.unique_id == f"{DOMAIN}_api_commands_lock-1"


async def test_real_setup_meters_requests_and_registers_entities(hass):
    """Full setup: requests made during setup are counted, entities registered."""
    entry = make_config_entry(options={CONF_PUSH_ENABLED: False})
    entry.add_to_hass(hass)
    lock = {"id": "lock-1", "name": "Front", "handleType": "utec-lock", "category": "lock"}
    with patch("custom_components.u_tec.UHomeApi") as mock_cls, patch(
        "custom_components.u_tec.config_entry_oauth2_flow.async_get_config_entry_implementation"
    ), patch("custom_components.u_tec.config_entry_oauth2_flow.OAuth2Session"), patch(
        "custom_components.u_tec.aiohttp_client.async_get_clientsession",
        return_value=MagicMock(),
    ), patch(
        "custom_components.u_tec.coordinator.UhomeDataUpdateCoordinator.async_start_periodic_discovery",
    ):
        instance = MagicMock()
        instance.discover_devices = AsyncMock(return_value={"payload": {"devices": [lock]}})
        instance.get_device_state = AsyncMock(return_value={"payload": {"devices": [{"id": "lock-1"}]}})
        mock_cls.return_value = instance
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    # 1 discovery + initial state fetch + first refresh
    assert coordinator.stats.requests[KIND_DISCOVERY] == 1
    assert coordinator.stats.requests[KIND_QUERY] == 2

    registry = er.async_get(hass)
    requests_id = registry.async_get_entity_id(
        "sensor", DOMAIN, f"{DOMAIN}_api_requests_{entry.entry_id}"
    )
    assert requests_id == "sensor.u_tec_integration_api_requests"
    assert hass.states.get(requests_id).state == "3"
    latency = registry.async_get(
        registry.async_get_entity_id(
            "sensor", DOMAIN, f"{DOMAIN}_api_last_latency_{entry.entry_id}"
        )
    )
    assert latency.disabled_by is er.RegistryEntryDisabler.INTEGRATION
    per_device = registry.async_get(
        registry.async_get_entity_id("sensor", DOMAIN, f"{DOMAIN}_api_commands_lock-1")
    )
    assert per_device.disabled_by is er.RegistryEntryDisabler.INTEGRATION
    assert per_device.entity_category == "diagnostic"

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
