"""Adaptive Aggressive accounting: the caught-change warning and AA stats."""

import logging
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.util import dt as dt_util

from custom_components.u_tec.adaptive import AdaptivePoller, reported_locked
from custom_components.u_tec.const import ADAPTIVE_AGGRESSIVE_MAX_ATTEMPTS
from custom_components.u_tec.coordinator import UhomeDataUpdateCoordinator
from custom_components.u_tec.sensor import AA_STAT_SENSORS
from custom_components.u_tec.stats import AdaptiveStats
from tests.common import make_config_entry

LOCKED = {"st.lock": {"lockState": "Locked"}}
UNLOCKED = {"st.lock": {"lockState": "Unlocked"}}
RAW_LOCKED = [{"capability": "st.lock", "name": "lockState", "value": "locked"}]
OK = {"payload": {"devices": [{"id": "lock-1"}]}}


def _coordinator(idle=20):
    coord = MagicMock()
    coord.update_interval = timedelta(seconds=idle)
    coord.devices = {}
    coord.data = {}
    coord.consecutive_update_failures = 0
    coord.api.get_device_state = AsyncMock(return_value=OK)
    return coord


def _lock(coord, state, name="Front Door"):
    device = MagicMock()
    device.name = name
    device.get_state_data.return_value = state
    device.update_state_data = AsyncMock()
    coord.devices["lock-1"] = device
    return device


@pytest.fixture
def scheduled():
    calls = []

    def fake_call_later(hass, delay, action):
        entry = {"delay": delay, "action": action}
        calls.append(entry)
        return lambda: None

    with (
        patch("custom_components.u_tec.adaptive.async_call_later", fake_call_later),
        patch("custom_components.u_tec.adaptive.async_dispatcher_send"),
    ):
        yield calls


async def _fire(entry):
    await entry["action"](None)


def _change_on_poll(device, poll_number, new_state):
    """Make the API report new_state starting on the given burst poll."""
    seen = {"n": 0}

    async def _update(_data):
        seen["n"] += 1
        if seen["n"] >= poll_number:
            device.get_state_data.return_value = new_state

    device.update_state_data = AsyncMock(side_effect=_update)


async def test_burst_catch_logs_warning_and_counts(scheduled, caplog):
    coord = _coordinator()
    device = _lock(coord, UNLOCKED)
    _change_on_poll(device, 4, LOCKED)
    poller = AdaptivePoller(coord)
    poller.start("lock-1", True)
    poller._bursts["lock-1"]["started_at"] = dt_util.utcnow() - timedelta(seconds=4.2)

    with caplog.at_level(logging.WARNING, logger="custom_components.u_tec.adaptive"):
        for _ in range(4):
            await _fire(scheduled[-1])

    assert not poller.is_running("lock-1")
    caught = [r for r in caplog.records if "caught" in r.getMessage()]
    assert len(caught) == 1
    message = caught[0].getMessage()
    assert caught[0].levelno == logging.WARNING
    assert "Front Door (lock-1) changing to locked" in message
    assert "after the command" in message
    assert f"on burst poll 4 of {ADAPTIVE_AGGRESSIVE_MAX_ATTEMPTS}" in message
    assert "(intervals: 1+1+1+1s)" in message

    stats = poller.stats
    assert stats.bursts_started == 1
    assert stats.polls == 4
    assert stats.changes_caught == 1
    assert stats.avg_polls_to_detect == 4
    assert 4.2 <= stats.avg_seconds_to_detect < 6
    assert stats.last_caught["state"] == "locked"


async def test_confirm_without_change_is_quiet(scheduled, caplog):
    """Locking an already locked door: the burst confirms, nothing changed."""
    coord = _coordinator()
    _lock(coord, LOCKED)
    poller = AdaptivePoller(coord)
    poller.start("lock-1", True)
    with caplog.at_level(logging.WARNING, logger="custom_components.u_tec.adaptive"):
        await _fire(scheduled[-1])
    assert not poller.is_running("lock-1")
    assert not [r for r in caplog.records if "caught" in r.getMessage()]
    assert poller.stats.changes_caught == 0
    assert poller.stats.confirmed_without_change == 1
    assert poller.stats.avg_seconds_to_detect is None


async def test_rearm_catch_says_recheck(scheduled, caplog):
    coord = _coordinator()
    device = _lock(coord, LOCKED)
    poller = AdaptivePoller(coord)
    poller.start("lock-1", False, clear_confirmation=False)
    _change_on_poll(device, 1, UNLOCKED)
    with caplog.at_level(logging.WARNING, logger="custom_components.u_tec.adaptive"):
        await _fire(scheduled[-1])
    assert "after the re-check started" in caplog.text
    assert poller.stats.rearms == 1


def test_push_and_regular_poll_endings_are_counted(scheduled):
    coord = _coordinator()
    device = _lock(coord, UNLOCKED)
    poller = AdaptivePoller(coord)

    poller.start("lock-1", True)
    poller.cancel_if_confirmed("lock-1", device, reason="push", state_data=LOCKED)
    poller.start("lock-1", True)
    poller.cancel_if_confirmed("lock-1", device, state_data=LOCKED)

    assert poller.stats.ended_by_push == 1
    assert poller.stats.ended_by_poll == 1
    assert poller.stats.changes_caught == 0


async def test_failures_and_exhaustion_are_counted(scheduled):
    coord = _coordinator(idle=60)
    _lock(coord, UNLOCKED)
    poller = AdaptivePoller(coord)

    poller.start("lock-1", True)
    for _ in range(ADAPTIVE_AGGRESSIVE_MAX_ATTEMPTS):
        await _fire(scheduled[-1])
    assert poller.stats.exhausted == 1
    assert poller.stats.polls == ADAPTIVE_AGGRESSIVE_MAX_ATTEMPTS

    coord.api.get_device_state.side_effect = RuntimeError("500")
    poller.start("lock-1", True)
    await _fire(scheduled[-1])
    await _fire(scheduled[-1])
    assert poller.stats.ended_by_failures == 1
    assert poller.stats.poll_failures == 2


def test_cancelled_bursts_are_counted_separately(scheduled):
    coord = _coordinator()
    _lock(coord, UNLOCKED)
    poller = AdaptivePoller(coord)
    poller.start("lock-1", True)
    poller.start("lock-1", False)  # restarted
    poller.cancel_all("debug polling")
    stats = poller.stats.as_dict()
    assert stats["bursts_started"] == 2
    assert stats["ended"]["cancelled"] == 2


def test_adaptive_stats_dict_shape():
    stats = AdaptiveStats()
    stats.record_start(rearm=False)
    stats.record_poll(ok=True)
    stats.record_caught("lock-1", 3.0, 3, "locked")
    stats.record_caught("lock-1", 6.0, 5, "unlocked")
    data = stats.as_dict()
    assert data["avg_seconds_to_detect"] == 4.5
    assert data["avg_polls_to_detect"] == 4
    assert set(data["ended"]) == {
        "caught_by_burst",
        "confirmed_without_change",
        "regular_poll",
        "push",
        "failures",
        "schedule_exhausted",
        "cancelled",
    }


def test_aa_sensors_read_adaptive_stats():
    stats = AdaptiveStats()
    stats.record_start(rearm=False)
    stats.record_poll(ok=True)
    stats.record_caught("lock-1", 2.0, 1, "locked")
    stats.record_end("push")
    stats.record_end("api errors")
    stats.record_end("idle cap")
    coord = SimpleNamespace(adaptive=SimpleNamespace(stats=stats))
    values = {d.key: d.value_fn(coord) for d in AA_STAT_SENSORS}
    assert values == {
        "aa_bursts_started": 1,
        "aa_polls": 1,
        "aa_changes_caught": 1,
        "aa_avg_seconds_to_detect": 2.0,
        "aa_avg_polls_to_detect": 1.0,
        "aa_ended_by_push": 1,
        "aa_ended_by_failures": 1,
        "aa_exhausted": 1,
    }


async def test_regular_poll_ends_burst_as_poll(hass, mock_uhome_api):
    entry = make_config_entry()
    entry.add_to_hass(hass)
    coord = UhomeDataUpdateCoordinator(
        hass, mock_uhome_api, config_entry=entry, scan_interval=20, discovery_interval=300,
    )
    device = MagicMock()
    device.get_state_data.return_value = UNLOCKED
    device.update_state_data = AsyncMock()
    coord.devices["lock-1"] = device
    with patch("custom_components.u_tec.adaptive.async_call_later", return_value=lambda: None):
        coord.adaptive.start("lock-1", True)
    device.get_state_data.return_value = LOCKED
    mock_uhome_api.get_device_state.return_value = {
        "payload": {"devices": [{"id": "lock-1", "states": RAW_LOCKED}]}
    }
    await coord._async_update_data()
    assert coord.adaptive.stats.ended_by_poll == 1
    assert not coord.adaptive.is_running("lock-1")


async def test_raw_push_ends_burst_as_push(hass, mock_uhome_api):
    """Pushes arrive as raw device dicts with a states list."""
    entry = make_config_entry()
    entry.add_to_hass(hass)
    coord = UhomeDataUpdateCoordinator(
        hass, mock_uhome_api, config_entry=entry, scan_interval=20, discovery_interval=300,
    )
    device = MagicMock()
    device.get_state_data.return_value = UNLOCKED
    device.update_state_data = AsyncMock()
    coord.devices["lock-1"] = device
    with patch("custom_components.u_tec.adaptive.async_call_later", return_value=lambda: None):
        coord.adaptive.start("lock-1", True)
    await coord.update_push_data([{"id": "lock-1", "states": RAW_LOCKED}])
    assert coord.adaptive.stats.ended_by_push == 1
    assert not coord.adaptive.is_running("lock-1")


def test_reported_locked_reads_raw_and_flat_shapes():
    assert reported_locked({"id": "x", "states": RAW_LOCKED}) is True
    assert reported_locked({"states": [{"capability": "st.lock", "name": "lockState", "value": "unlocked"}]}) is False
    assert reported_locked({"states": [{"capability": "st.batteryLevel", "name": "level", "value": 3}]}) is None
    assert reported_locked(LOCKED) is True
