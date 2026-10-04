"""Security commands are never recommendations.

Lock and unlock always reach the API, or are verified with a fresh query
first. Nothing skips them because of cached or perceived state.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.u_tec.const import (
    CONF_OPTIMISTIC_LOCKS,
    CONF_PUSH_ENABLED,
    DOMAIN,
)
from custom_components.u_tec.lock import UhomeLockEntity
from custom_components.u_tec.optimistic import CONF_ADAPTIVE_AGGRESSIVE_LOCKS
from tests.common import make_config_entry, make_fake_lock

LOCK = {"id": "lock-1", "name": "Front", "handleType": "utec-lock", "category": "lock"}


def _states(lock_state="locked", online=True, mode=0):
    return {"payload": {"devices": [{"id": "lock-1", "states": [
        {"capability": "st.lock", "name": "lockState", "value": lock_state.capitalize()},
        {"capability": "st.lock", "name": "lockMode", "value": mode},
        {"capability": "st.healthCheck", "name": "status", "value": "Online" if online else "Offline"},
    ]}]}}


async def _setup(hass, state_reply, options=None):
    entry = make_config_entry(options={CONF_PUSH_ENABLED: False, **(options or {})})
    entry.add_to_hass(hass)
    instance = MagicMock()
    instance.discover_devices = AsyncMock(return_value={"payload": {"devices": [LOCK]}})
    instance.get_device_state = AsyncMock(return_value=state_reply)
    instance.query_device = AsyncMock(return_value=state_reply)
    instance.send_command = AsyncMock(return_value={"payload": {}})
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
    return entry, instance


def _sent(instance):
    return [c.args[2] for c in instance.send_command.await_args_list]


@pytest.mark.parametrize("optimistic", [True, False])
@pytest.mark.parametrize(
    ("cached", "service", "command"),
    [("locked", "lock", "lock"), ("unlocked", "unlock", "unlock")],
)
async def test_command_sent_when_cached_state_already_matches(
    hass, optimistic, cached, service, command
):
    entry, instance = await _setup(
        hass,
        _states(cached),
        {CONF_OPTIMISTIC_LOCKS: optimistic, CONF_ADAPTIVE_AGGRESSIVE_LOCKS: True},
    )
    assert hass.states.get("lock.front_front").state == cached

    await hass.services.async_call("lock", service, {"entity_id": "lock.front_front"}, blocking=True)
    await hass.services.async_call("lock", service, {"entity_id": "lock.front_front"}, blocking=True)

    assert _sent(instance) == [command, command]
    await hass.config_entries.async_unload(entry.entry_id)


@pytest.mark.parametrize("service", ["lock", "unlock"])
async def test_command_sent_when_lock_last_reported_offline(hass, service):
    """Home Assistant drops calls to unavailable entities, so stay available."""
    entry, instance = await _setup(hass, _states("unlocked", online=False))
    state = hass.states.get("lock.front_front")
    assert state.state == "unknown"
    assert state.attributes["status_current"] is False

    await hass.services.async_call("lock", service, {"entity_id": "lock.front_front"}, blocking=True)

    assert _sent(instance) == [service]
    await hass.config_entries.async_unload(entry.entry_id)


@pytest.mark.parametrize("service", ["lock", "unlock"])
async def test_command_sent_when_polls_are_failing(hass, service):
    entry, instance = await _setup(hass, _states("locked"))
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    coordinator.consecutive_update_failures = 5
    coordinator.async_update_listeners()
    await hass.async_block_till_done()
    assert hass.states.get("lock.front_front").state == "unknown"

    await hass.services.async_call("lock", service, {"entity_id": "lock.front_front"}, blocking=True)

    assert _sent(instance) == [service]
    await hass.config_entries.async_unload(entry.entry_id)


async def test_command_sent_during_debug_polling(hass):
    entry, instance = await _setup(hass, _states("locked"))
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    coordinator.debug.start()
    await hass.services.async_call("lock", "lock", {"entity_id": "lock.front_front"}, blocking=True)
    await hass.services.async_call("lock", "unlock", {"entity_id": "lock.front_front"}, blocking=True)
    assert _sent(instance) == ["lock", "unlock"]
    coordinator.debug.stop()
    await hass.config_entries.async_unload(entry.entry_id)


async def test_cached_passage_is_verified_not_trusted(hass):
    """Cache says Passage, fresh query says Normal: the lock command is sent."""
    entry, instance = await _setup(hass, _states("unlocked", mode=1))
    instance.query_device = AsyncMock(return_value=_states("unlocked", mode=0))
    await hass.services.async_call("lock", "lock", {"entity_id": "lock.front_front"}, blocking=True)
    instance.query_device.assert_awaited_once_with("lock-1")
    assert _sent(instance) == ["lock"]
    await hass.config_entries.async_unload(entry.entry_id)


def test_unit_unlock_sent_with_cached_unlocked_and_stale_status():
    entry = make_config_entry(options={CONF_OPTIMISTIC_LOCKS: True})
    lock = make_fake_lock("lock-1", is_locked=False, available=False)
    coord = MagicMock()
    coord.devices = {"lock-1": lock}
    coord.config_entry = entry
    coord.poll_healthy_enough = False
    ent = UhomeLockEntity(coord, "lock-1")
    assert ent.available is True
    assert ent.is_locked is None
    assert ent.is_jammed is None
