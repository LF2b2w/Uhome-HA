"""Debug Polling Mode: 1s polling for a hard-limited 120s session."""

import logging
from datetime import timedelta
from types import MappingProxyType
from unittest.mock import MagicMock, patch

import pytest
import voluptuous as vol
from homeassistant.exceptions import ConfigEntryAuthFailed, ServiceValidationError
from homeassistant.helpers.update_coordinator import UpdateFailed
from pytest_homeassistant_custom_component.common import async_fire_time_changed
from utec_client.exceptions import ApiError, AuthenticationError

from custom_components.u_tec import (
    async_setup,
    async_setup_entry,
    async_update_options,
)
from custom_components.u_tec.binary_sensor import UhomeDebugPollingSensor
from custom_components.u_tec.button import (
    UhomeStartDebugPollingButton,
    UhomeStopDebugPollingButton,
)
from custom_components.u_tec.const import (
    CONF_OPTIMISTIC_LIGHTS,
    CONF_OPTIMISTIC_LOCKS,
    CONF_OPTIMISTIC_SWITCHES,
    CONF_PUSH_ENABLED,
    CONF_SCAN_INTERVAL,
    DEBUG_POLL_DURATION,
    DEBUG_POLL_INTERVAL,
    DOMAIN,
    SERVICE_START_DEBUG_POLLING,
    SERVICE_STOP_DEBUG_POLLING,
)
from custom_components.u_tec.coordinator import UhomeDataUpdateCoordinator
from custom_components.u_tec.debug_polling import (
    REASON_EXPIRED,
    REASON_FAILURES,
    REASON_STOPPED,
    debug_polling_active,
)
from custom_components.u_tec.light import UhomeLightEntity
from custom_components.u_tec.lock import UhomeLockEntity
from custom_components.u_tec.switch import UhomeSwitchEntity
from tests.common import (
    make_config_entry,
    make_fake_light,
    make_fake_lock,
    make_fake_switch,
)
from tests.test_setup import _patched_setup_env, patched_uhomeapi  # noqa: F401

NORMAL = timedelta(seconds=30)
STATE_RESPONSE = {"payload": {"devices": [{"id": "sw-1", "states": []}]}}


@pytest.fixture
async def coordinator(hass, mock_uhome_api):
    entry = make_config_entry(options={CONF_SCAN_INTERVAL: 30})
    entry.add_to_hass(hass)
    coord = UhomeDataUpdateCoordinator(
        hass, mock_uhome_api, config_entry=entry, scan_interval=30, discovery_interval=300,
    )
    switch = make_fake_switch("sw-1")
    switch.get_state_data = dict
    coord.devices["sw-1"] = switch
    mock_uhome_api.get_device_state.return_value = STATE_RESPONSE
    yield coord
    coord.debug.shutdown()
    await coord.async_shutdown()


def test_helper_ignores_stub_coordinators():
    assert debug_polling_active(MagicMock()) is False
    assert debug_polling_active(None) is False


async def test_start_switches_to_one_second_and_logs(coordinator, caplog):
    caplog.set_level(logging.WARNING)
    with patch.object(coordinator.adaptive, "cancel_all") as cancel_all:
        assert coordinator.debug.start() is True

    assert coordinator.debug_polling_active is True
    assert coordinator.update_interval == timedelta(seconds=DEBUG_POLL_INTERVAL)
    assert coordinator.debug.ends_at - coordinator.debug.started_at == timedelta(
        seconds=DEBUG_POLL_DURATION
    )
    cancel_all.assert_called_once_with("debug polling")
    assert any(
        r.levelname == "WARNING" and "debug polling started" in r.getMessage()
        for r in caplog.records
    )


async def test_session_expires_at_120s_and_restores_interval(
    hass, coordinator, freezer, caplog,
):
    caplog.set_level(logging.WARNING)
    coordinator.debug.start()

    freezer.tick(timedelta(seconds=DEBUG_POLL_DURATION - 1))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert coordinator.debug.active is True

    freezer.tick(timedelta(seconds=1))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    assert coordinator.debug.active is False
    assert coordinator.update_interval == NORMAL
    assert coordinator.debug.last_session["reason"] == REASON_EXPIRED
    assert any(
        r.levelname == "WARNING" and f"stopped ({REASON_EXPIRED})" in r.getMessage()
        for r in caplog.records
    )


async def test_repress_while_active_does_not_extend(hass, coordinator, freezer):
    coordinator.debug.start()
    ends_at = coordinator.debug.ends_at

    freezer.tick(timedelta(seconds=60))
    assert coordinator.debug.start() is False
    assert coordinator.debug.ends_at == ends_at

    freezer.tick(timedelta(seconds=60))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert coordinator.debug.active is False


async def test_poll_guard_ends_session_past_deadline(coordinator, freezer):
    """Even if the expiry timer were lost, the next poll enforces the limit."""
    coordinator.debug.start()
    coordinator.debug._unsub_expire()
    coordinator.debug._unsub_expire = None

    freezer.tick(timedelta(seconds=DEBUG_POLL_DURATION))
    await coordinator._async_update_data()

    assert coordinator.debug.active is False
    assert coordinator.update_interval == NORMAL


async def test_polls_every_second_then_returns_to_normal(
    hass, coordinator, mock_uhome_api, freezer, caplog,
):
    caplog.set_level(logging.WARNING)
    unsub = coordinator.async_add_listener(lambda: None)
    coordinator.debug.start()

    for _ in range(5):
        freezer.tick(timedelta(seconds=1.1))
        async_fire_time_changed(hass)
        await hass.async_block_till_done()
    assert mock_uhome_api.get_device_state.await_count >= 4
    assert coordinator.debug.requests == mock_uhome_api.get_device_state.await_count

    coordinator.debug.stop()
    assert coordinator.update_interval == NORMAL
    stopped = [r.getMessage() for r in caplog.records if "debug polling stopped" in r.getMessage()]
    assert stopped and f"after {coordinator.debug.last_session['requests']} request(s)" in stopped[0]

    calls = mock_uhome_api.get_device_state.await_count
    freezer.tick(timedelta(seconds=10))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert mock_uhome_api.get_device_state.await_count == calls
    unsub()


async def test_adaptive_aggressive_paused_then_restored(coordinator):
    with patch.object(coordinator.adaptive, "start") as start:
        coordinator.debug.start()
        coordinator.start_adaptive_poll("lock-1", True)
        start.assert_not_called()

        coordinator.debug.stop()
        coordinator.start_adaptive_poll("lock-1", True)
        start.assert_called_once_with("lock-1", True)


async def test_contradiction_hold_is_off_during_debug(coordinator):
    with patch.object(
        coordinator.adaptive, "contradicts_confirmation", return_value=True,
    ), patch.object(coordinator.adaptive, "rearm_for_confirmation") as rearm:
        coordinator.debug.start()
        assert coordinator._defer_contradicting_report("lock-1", {}) is False
        rearm.assert_not_called()


async def test_push_is_stamped_but_not_applied(coordinator):
    switch = coordinator.devices["sw-1"]
    coordinator.consecutive_update_failures = 1
    coordinator.debug.start()

    await coordinator.update_push_data([{"id": "sw-1", "states": []}])

    assert coordinator.last_push_received is not None
    switch.update_state_data.assert_not_awaited()
    assert coordinator.consecutive_update_failures == 1

    coordinator.debug.stop()
    await coordinator.update_push_data([{"id": "sw-1", "states": []}])
    switch.update_state_data.assert_awaited_once()
    assert coordinator.consecutive_update_failures == 0


async def test_failure_threshold_ends_session(coordinator, mock_uhome_api):
    coordinator.debug.start()
    mock_uhome_api.get_device_state.side_effect = ApiError(500, "blip")

    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()
    assert coordinator.debug.active is True  # one blip is tolerated

    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()
    assert coordinator.debug.active is False
    assert coordinator.update_interval == NORMAL
    assert coordinator.debug.last_session["reason"] == REASON_FAILURES
    assert coordinator.debug.last_session["requests"] == 2


async def test_auth_failure_ends_session_immediately(coordinator, mock_uhome_api):
    coordinator.debug.start()
    mock_uhome_api.get_device_state.side_effect = AuthenticationError("expired")
    with pytest.raises(ConfigEntryAuthFailed):
        await coordinator._async_update_data()
    assert coordinator.debug.active is False
    assert coordinator.update_interval == NORMAL


async def test_stop_is_idempotent(coordinator):
    assert coordinator.debug.stop() is False
    coordinator.debug.start()
    assert coordinator.debug.stop() is True
    assert coordinator.debug.last_session["reason"] == REASON_STOPPED
    assert coordinator.debug.stop() is False


async def test_options_saved_during_session_apply_at_end(
    hass, patched_uhomeapi,  # noqa: F811
):
    entry = make_config_entry(options={CONF_PUSH_ENABLED: False, CONF_SCAN_INTERVAL: 30})
    entry.add_to_hass(hass)
    with _patched_setup_env(hass):
        await async_setup_entry(hass, entry)
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    coordinator.debug.start()

    object.__setattr__(entry, "options", MappingProxyType({
        CONF_PUSH_ENABLED: False, CONF_SCAN_INTERVAL: 60,
    }))
    await async_update_options(hass, entry)
    assert coordinator.update_interval == timedelta(seconds=DEBUG_POLL_INTERVAL)

    coordinator.debug.stop()
    assert coordinator.update_interval == timedelta(seconds=60)
    await coordinator.async_shutdown()


async def test_session_is_never_persisted(hass, patched_uhomeapi):  # noqa: F811
    options = {CONF_PUSH_ENABLED: False, CONF_SCAN_INTERVAL: 30}
    entry = make_config_entry(options=options)
    entry.add_to_hass(hass)
    with _patched_setup_env(hass):
        await async_setup_entry(hass, entry)
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    coordinator.debug.start()
    assert dict(entry.options) == options

    # Unload hook ends the session; a fresh setup starts at the normal interval.
    coordinator.debug.shutdown()
    assert coordinator.debug.active is False
    with _patched_setup_env(hass):
        await async_setup_entry(hass, entry)
    reloaded = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    assert reloaded is not coordinator
    assert reloaded.debug.active is False
    assert reloaded.update_interval == NORMAL
    assert dict(entry.options) == options
    await coordinator.async_shutdown()


async def test_services_start_and_stop(hass, patched_uhomeapi):  # noqa: F811
    assert await async_setup(hass, {})
    entry = make_config_entry(options={CONF_PUSH_ENABLED: False})
    entry.add_to_hass(hass)
    with _patched_setup_env(hass):
        await async_setup_entry(hass, entry)
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]

    await hass.services.async_call(DOMAIN, SERVICE_START_DEBUG_POLLING, {}, blocking=True)
    assert coordinator.debug.active is True
    await hass.services.async_call(
        DOMAIN,
        SERVICE_STOP_DEBUG_POLLING,
        {"config_entry_id": entry.entry_id},
        blocking=True,
    )
    assert coordinator.debug.active is False
    await coordinator.async_shutdown()

    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_START_DEBUG_POLLING,
            {"config_entry_id": "nope"},
            blocking=True,
        )
    with pytest.raises(vol.Invalid):  # no duration field, on purpose
        await hass.services.async_call(
            DOMAIN, SERVICE_START_DEBUG_POLLING, {"duration": 600}, blocking=True,
        )


async def test_services_with_nothing_loaded(hass):
    assert await async_setup(hass, {})
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN, SERVICE_START_DEBUG_POLLING, {}, blocking=True,
        )


async def test_buttons_and_diagnostic_sensor(coordinator):
    start = UhomeStartDebugPollingButton(coordinator)
    stop = UhomeStopDebugPollingButton(coordinator)
    sensor = UhomeDebugPollingSensor(coordinator)
    entry_id = coordinator.config_entry.entry_id
    assert start.unique_id == f"{DOMAIN}_start_debug_polling_{entry_id}"
    assert stop.unique_id == f"{DOMAIN}_stop_debug_polling_{entry_id}"
    assert sensor.available is True
    assert sensor.is_on is False

    await start.async_press()
    assert sensor.is_on is True
    await coordinator._async_update_data()
    attrs = sensor.extra_state_attributes
    assert attrs["requests"] == 1
    assert attrs["ends_at"] == coordinator.debug.ends_at.isoformat()

    await stop.async_press()
    assert sensor.is_on is False
    attrs = sensor.extra_state_attributes
    assert attrs["ends_at"] is None
    assert attrs["requests"] == 1
    assert attrs["last_stop_reason"] == REASON_STOPPED


def _entity_coord(hass, device, options):
    entry = make_config_entry(options=options)
    entry.add_to_hass(hass)
    coord = MagicMock()
    coord.devices = {device.device_id: device}
    coord.config_entry = entry
    coord.poll_healthy_enough = True
    coord.data = {}
    coord.debug_polling_active = False
    return coord


def _attach(ent, hass, entity_id):
    ent.hass = hass
    ent.entity_id = entity_id
    ent.async_write_ha_state = MagicMock()
    return ent


async def test_lock_optimism_off_during_debug_and_back_after(hass):
    lock = make_fake_lock("lock-1", is_locked=False)
    coord = _entity_coord(hass, lock, {CONF_OPTIMISTIC_LOCKS: True})
    ent = _attach(UhomeLockEntity(coord, "lock-1"), hass, "lock.fake_lock")

    await ent.async_lock()
    assert ent.is_locked is True and ent.assumed_state is True

    coord.debug_polling_active = True
    ent._handle_coordinator_update()
    assert ent.is_locked is False  # raw polled state
    assert ent.assumed_state is False
    await ent.async_lock()
    assert ent.is_locked is False

    coord.debug_polling_active = False
    await ent.async_lock()
    assert ent.is_locked is True and ent.assumed_state is True


async def test_switch_optimism_off_during_debug(hass):
    switch = make_fake_switch("sw-1", is_on=False)
    coord = _entity_coord(hass, switch, {CONF_OPTIMISTIC_SWITCHES: True})
    ent = _attach(UhomeSwitchEntity(coord, "sw-1"), hass, "switch.fake_switch")

    await ent.async_turn_on()
    assert ent.is_on is True

    coord.debug_polling_active = True
    ent._handle_coordinator_update()
    assert ent.is_on is False
    await ent.async_turn_on()
    assert ent.is_on is False

    coord.debug_polling_active = False
    await ent.async_turn_on()
    assert ent.is_on is True


async def test_light_optimism_off_during_debug(hass):
    light = make_fake_light("light-1", is_on=False, brightness=10)
    coord = _entity_coord(hass, light, {CONF_OPTIMISTIC_LIGHTS: True})
    ent = _attach(UhomeLightEntity(coord, "light-1"), hass, "light.fake_light")

    await ent.async_turn_on(brightness=255)
    assert ent.is_on is True

    coord.debug_polling_active = True
    ent._handle_coordinator_update()
    assert ent.is_on is False
    assert ent._optimistic_brightness is None
    await ent.async_turn_on()
    assert ent.is_on is False

    coord.debug_polling_active = False
    await ent.async_turn_on()
    assert ent.is_on is True


async def test_entities_registered_on_real_setup(hass, patched_uhomeapi):  # noqa: F811
    """Full platform setup creates the buttons and the diagnostic sensor."""
    from homeassistant.helpers import entity_registry as er

    entry = make_config_entry(options={CONF_PUSH_ENABLED: False})
    entry.add_to_hass(hass)
    with patch(
        "custom_components.u_tec.config_entry_oauth2_flow.async_get_config_entry_implementation"
    ), patch("custom_components.u_tec.config_entry_oauth2_flow.OAuth2Session"), patch(
        "custom_components.u_tec.aiohttp_client.async_get_clientsession",
        return_value=MagicMock(),
    ), patch(
        "custom_components.u_tec.coordinator.UhomeDataUpdateCoordinator.async_start_periodic_discovery",
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    registry = er.async_get(hass)
    start_id = registry.async_get_entity_id(
        "button", DOMAIN, f"{DOMAIN}_start_debug_polling_{entry.entry_id}"
    )
    sensor_id = registry.async_get_entity_id(
        "binary_sensor", DOMAIN, f"{DOMAIN}_debug_polling_{entry.entry_id}"
    )
    assert start_id == "button.u_tec_integration_start_debug_polling"
    assert hass.states.get(sensor_id).state == "off"

    await hass.services.async_call(
        "button", "press", {"entity_id": start_id}, blocking=True
    )
    await hass.async_block_till_done()
    assert hass.states.get(sensor_id).state == "on"
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    assert coordinator.update_interval == timedelta(seconds=DEBUG_POLL_INTERVAL)

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert coordinator.debug.active is False
    assert entry.entry_id not in hass.data[DOMAIN]
    assert CONF_SCAN_INTERVAL not in entry.options
