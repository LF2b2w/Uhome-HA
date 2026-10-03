"""Adaptive Aggressive confirmation bursts.

The timer math and stop rules do not need a running Home Assistant. The
poller is driven by stubbing async_call_later and invoking the saved callback.
"""

from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import asyncio
import pytest

from custom_components.u_tec.adaptive import (
    AdaptivePoller,
    confirmation_delays,
    next_fibonacci_delay,
)
from custom_components.u_tec.const import (
    ADAPTIVE_AGGRESSIVE_INITIAL_DELAY,
    ADAPTIVE_AGGRESSIVE_MAX_ATTEMPTS,
)
from custom_components.u_tec.optimistic import (
    CONF_ADAPTIVE_AGGRESSIVE_LOCKS,
    DEFAULT_ADAPTIVE_AGGRESSIVE,
    is_adaptive_aggressive_enabled,
)


def test_default_is_off():
    assert DEFAULT_ADAPTIVE_AGGRESSIVE is False
    assert is_adaptive_aggressive_enabled({}, "lock-1") is False


def test_true_enables_every_lock():
    options = {CONF_ADAPTIVE_AGGRESSIVE_LOCKS: True}
    assert is_adaptive_aggressive_enabled(options, "lock-1") is True


def test_list_enables_only_listed_locks():
    options = {CONF_ADAPTIVE_AGGRESSIVE_LOCKS: ["lock-2"]}
    assert is_adaptive_aggressive_enabled(options, "lock-1") is False
    assert is_adaptive_aggressive_enabled(options, "lock-2") is True


def test_fibonacci_sequence_matches_constants():
    seen = confirmation_delays()
    assert seen[0] == ADAPTIVE_AGGRESSIVE_INITIAL_DELAY
    assert len(seen) == ADAPTIVE_AGGRESSIVE_MAX_ATTEMPTS
    assert seen == [1, 2, 3, 5, 8]


def _coordinator(idle=20):
    coord = MagicMock()
    coord.update_interval = timedelta(seconds=idle)
    coord.hass = MagicMock()
    coord.devices = {}
    coord.data = {}
    coord.consecutive_update_failures = 0
    coord.api.get_device_state = AsyncMock()
    return coord


@pytest.fixture
def scheduled():
    calls = []

    def fake_call_later(hass, delay, action):
        entry = {"delay": delay, "action": action, "cancelled": False}

        def cancel():
            entry["cancelled"] = True

        calls.append(entry)
        return cancel

    with (
        patch("custom_components.u_tec.adaptive.async_call_later", fake_call_later),
        patch("custom_components.u_tec.adaptive.async_dispatcher_send"),
    ):
        yield calls


async def _fire(entry):
    await entry["action"](None)


def test_start_schedules_initial_delay(scheduled):
    coord = _coordinator()
    poller = AdaptivePoller(coord)
    poller.start("lock-1", True)
    assert scheduled[0]["delay"] == 1
    assert "lock-1" in poller._bursts


def test_start_refuses_when_idle_is_not_longer_than_initial(scheduled):
    coord = _coordinator(idle=1)
    poller = AdaptivePoller(coord)
    poller.start("lock-1", True)
    assert scheduled == []
    assert poller._bursts == {}


async def test_confirms_and_stops(scheduled):
    coord = _coordinator()
    device = MagicMock()
    device.is_locked = False
    device.get_state_data.return_value = {"st.lock": {"lockState": "Unlocked"}}
    coord.devices["lock-1"] = device
    coord.api.get_device_state.return_value = {
        "payload": {"devices": [{"id": "lock-1"}]}
    }

    async def _update(data):
        device.is_locked = True
        device.get_state_data.return_value = {"st.lock": {"lockState": "Locked"}}

    device.update_state_data = AsyncMock(side_effect=_update)

    poller = AdaptivePoller(coord)
    poller.start("lock-1", True)
    await _fire(scheduled[0])

    assert "lock-1" not in poller._bursts
    coord.async_set_updated_data.assert_called_once()
    assert scheduled[0]["cancelled"] is False


async def test_fibonacci_reschedule_until_max_attempts(scheduled):
    coord = _coordinator(idle=60)
    device = MagicMock()
    device.is_locked = False
    device.get_state_data.return_value = {}
    device.update_state_data = AsyncMock()
    coord.devices["lock-1"] = device
    coord.api.get_device_state.return_value = {
        "payload": {"devices": [{"id": "lock-1"}]}
    }

    poller = AdaptivePoller(coord)
    poller.start("lock-1", True)
    delays = [scheduled[0]["delay"]]
    for _ in range(ADAPTIVE_AGGRESSIVE_MAX_ATTEMPTS):
        await _fire(scheduled[-1])
        if "lock-1" not in poller._bursts:
            break
        delays.append(scheduled[-1]["delay"])

    assert delays == confirmation_delays()
    assert not poller.is_running("lock-1")


async def test_stops_when_next_delay_would_meet_idle(scheduled):
    coord = _coordinator(idle=4)
    device = MagicMock()
    device.is_locked = False
    device.get_state_data.return_value = {}
    device.update_state_data = AsyncMock()
    coord.devices["lock-1"] = device
    coord.api.get_device_state.return_value = {
        "payload": {"devices": [{"id": "lock-1"}]}
    }

    poller = AdaptivePoller(coord)
    poller.start("lock-1", True)
    await _fire(scheduled[0])  # 1s, next would be 2
    assert "lock-1" in poller._bursts
    await _fire(scheduled[-1])  # 2s, next would be 3
    assert "lock-1" in poller._bursts
    await _fire(scheduled[-1])  # 3s, next would be 5 >= 4
    assert "lock-1" not in poller._bursts


def test_push_match_cancels_burst(scheduled):
    coord = _coordinator()
    device = MagicMock()
    device.get_state_data.return_value = {"st.lock": {"lockState": "Locked"}}
    coord.devices["lock-1"] = device
    poller = AdaptivePoller(coord)
    poller.start("lock-1", True)
    poller.cancel_if_confirmed(
        "lock-1",
        device,
        reason="push",
        state_data={"st.lock": {"lockState": "Locked"}},
    )
    assert "lock-1" not in poller._bursts
    assert scheduled[0]["cancelled"] is True
    assert poller.young_confirmation("lock-1")["locked"] is True


def test_push_mismatch_leaves_burst_running(scheduled):
    coord = _coordinator()
    device = MagicMock()
    poller = AdaptivePoller(coord)
    poller.start("lock-1", True)
    poller.cancel_if_confirmed(
        "lock-1",
        device,
        reason="push",
        state_data={"st.lock": {"lockState": "Unlocked"}},
    )
    assert "lock-1" in poller._bursts
    assert scheduled[0]["cancelled"] is False


def test_partial_push_does_not_confirm_unlock(scheduled):
    coord = _coordinator()
    device = MagicMock()
    device.is_locked = False
    poller = AdaptivePoller(coord)
    poller.start("lock-1", False)
    poller.cancel_if_confirmed(
        "lock-1",
        device,
        reason="push",
        state_data={"st.battery": {"battery": 80}},
    )
    assert "lock-1" in poller._bursts


def test_contradicting_report_is_deferred(scheduled):
    coord = _coordinator(idle=20)
    device = MagicMock()
    device.get_state_data.return_value = {"st.lock": {"lockState": "Locked"}}
    coord.devices["lock-1"] = device
    poller = AdaptivePoller(coord)
    poller.start("lock-1", True)
    poller.cancel_if_confirmed(
        "lock-1",
        device,
        state_data={"st.lock": {"lockState": "Locked"}},
    )
    assert poller.contradicts_confirmation(
        "lock-1", {"st.lock": {"lockState": "Unlocked"}}
    )
    coord.config_entry.options = {CONF_ADAPTIVE_AGGRESSIVE_LOCKS: True}
    poller.rearm_for_confirmation("lock-1")
    assert poller.expected_locked("lock-1") is True
    assert scheduled[-1]["delay"] == 1


def test_new_command_supersedes_confirmation(scheduled):
    coord = _coordinator(idle=20)
    device = MagicMock()
    poller = AdaptivePoller(coord)
    poller.start("lock-1", True)
    poller.cancel_if_confirmed(
        "lock-1",
        device,
        state_data={"st.lock": {"lockState": "Locked"}},
    )
    poller.start("lock-1", False)
    assert poller.young_confirmation("lock-1") is None
    assert poller.expected_locked("lock-1") is False
    unlocked = {"st.lock": {"lockState": "Unlocked"}}
    assert poller.contradicts_confirmation("lock-1", unlocked) is False
    poller.cancel_if_confirmed("lock-1", device, reason="push", state_data=unlocked)
    assert not poller.is_running("lock-1")
    coord.hass.bus.async_fire.assert_not_called()


def test_rearm_stops_when_option_is_off(scheduled):
    coord = _coordinator(idle=20)
    coord.config_entry.options = {CONF_ADAPTIVE_AGGRESSIVE_LOCKS: False}
    device = MagicMock()
    poller = AdaptivePoller(coord)
    poller.start("lock-1", True)
    poller.cancel_if_confirmed(
        "lock-1",
        device,
        state_data={"st.lock": {"lockState": "Locked"}},
    )
    poller.rearm_for_confirmation("lock-1")
    assert not poller.is_running("lock-1")
    assert poller.young_confirmation("lock-1") is None


async def test_stale_tick_does_not_cancel_replacement(scheduled):
    coord = _coordinator()
    device = MagicMock()
    device.get_state_data.return_value = {"st.lock": {"lockState": "Unlocked"}}
    coord.devices["lock-1"] = device
    started = asyncio.Event()
    release = asyncio.Event()

    async def _hang(_ids, _arg):
        started.set()
        await release.wait()
        return {"payload": {"devices": [{"id": "lock-1"}]}}

    coord.api.get_device_state = AsyncMock(side_effect=_hang)
    poller = AdaptivePoller(coord)
    poller.start("lock-1", True)
    first = asyncio.create_task(_fire(scheduled[0]))
    await started.wait()
    poller.start("lock-1", False)
    release.set()
    await first
    assert poller._bursts["lock-1"]["expected_locked"] is False
