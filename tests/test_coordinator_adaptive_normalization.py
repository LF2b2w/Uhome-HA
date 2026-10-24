"""Adaptive helpers must receive normalized state, not raw U-Tec payloads.

Regression tests for the coordinator poll/push paths. U-Tec poll and push
replies carry raw device payloads shaped ``{"id", "states": [{"capability",
"name", "value"}]}``; the AdaptivePoller helpers (and
``lock_state.reported_locked``) read the client's normalized shape
``{"capability": {name: value}}``. Passing raw payloads made the
confirmation burst never stop on poll/push reports and disabled the
young-confirmation contradiction guard.

Every test drives the coordinator's real AdaptivePoller with a real
utec-client Lock; only the API transport is mocked. No Hypothesis, no
discovery-import collection — plain deterministic coroutines.
"""

from __future__ import annotations

from datetime import timedelta

from homeassistant.util import dt as dt_util
import pytest
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.u_tec.const import CONF_ADAPTIVE_AGGRESSIVE_LOCKS
from custom_components.u_tec.coordinator import UhomeDataUpdateCoordinator
from tests.common import make_config_entry
from utec_client.devices.lock import Lock as UhomeLock

LOCK_ID = "L1"


def _discovery(device_id: str = LOCK_ID) -> dict:
    """Discovery-shaped payload the real client Lock requires."""
    return {
        "id": device_id,
        "name": "Front Door",
        "handleType": "utec-lock",
        "category": "unknown",
        "deviceInfo": {"manufacturer": "U-Tec", "model": "M", "hwVersion": "1.0"},
    }


def _raw_state(device_id: str = LOCK_ID, locked: bool = True) -> dict:
    """Raw U-Tec state payload exactly as poll/push deliver it."""
    return {
        "id": device_id,
        "states": [
            {
                "capability": "st.lock",
                "name": "lockState",
                "value": "Locked" if locked else "Unlocked",
            }
        ],
    }


async def _make_device(mock_uhome_api, locked: bool) -> UhomeLock:
    """Real client Lock seeded with an initial locked/unlocked state."""
    lock = UhomeLock(_discovery(), mock_uhome_api)
    await lock.update_state_data(_raw_state(locked=locked))
    return lock


@pytest.fixture
async def coordinator(hass, mock_uhome_api):
    """Real coordinator (and its real AdaptivePoller) with adaptive enabled.

    scan_interval=10 keeps the burst alive (initial 1s delay < idle) and the
    confirmation window at 10s, far longer than a test runs.
    """
    entry = make_config_entry(options={CONF_ADAPTIVE_AGGRESSIVE_LOCKS: [LOCK_ID]})
    entry.add_to_hass(hass)
    coord = UhomeDataUpdateCoordinator(
        hass,
        mock_uhome_api,
        config_entry=entry,
        scan_interval=10,
        discovery_interval=300,
    )
    yield coord
    coord.async_stop_adaptive_polls()  # leave no pending burst timers behind


async def test_confirming_poll_stops_burst_and_records_confirmation(
    coordinator, mock_uhome_api
):
    """A poll report matching the commanded state stops the burst."""
    lock = await _make_device(mock_uhome_api, locked=False)
    coordinator.devices[LOCK_ID] = lock
    coordinator.start_adaptive_poll(LOCK_ID, expected_locked=True)
    assert coordinator.adaptive.is_running(LOCK_ID)

    mock_uhome_api.get_device_state.return_value = {
        "payload": {"devices": [_raw_state(locked=True)]}
    }
    await coordinator._async_update_data()

    assert not coordinator.adaptive.is_running(LOCK_ID)
    assert coordinator.adaptive.young_confirmation(LOCK_ID)["locked"] is True
    assert lock.lock_state == "Locked"  # confirming poll still applied


@pytest.mark.parametrize("push_devices", [[], [LOCK_ID]])
async def test_confirming_push_stops_burst_and_records_confirmation(
    coordinator, push_devices
):
    """An eligible push matching the commanded state stops the burst."""
    lock = await _make_device(coordinator.api, locked=False)
    coordinator.devices[LOCK_ID] = lock
    coordinator.push_devices = push_devices
    coordinator.start_adaptive_poll(LOCK_ID, expected_locked=True)
    assert coordinator.adaptive.is_running(LOCK_ID)

    await coordinator.update_push_data(
        {"payload": {"devices": [_raw_state(locked=True)]}}
    )

    assert not coordinator.adaptive.is_running(LOCK_ID)
    assert coordinator.adaptive.young_confirmation(LOCK_ID)["locked"] is True
    assert lock.lock_state == "Locked"  # confirming push still applied


@pytest.mark.parametrize("source", ["push", "poll"])
async def test_report_without_lock_evidence_does_not_confirm(
    coordinator, mock_uhome_api, source
):
    """An eligible report needs lock evidence to confirm an active burst."""
    lock = await _make_device(mock_uhome_api, locked=False)
    coordinator.devices[LOCK_ID] = lock
    coordinator.push_devices = [LOCK_ID]
    coordinator.start_adaptive_poll(LOCK_ID, expected_locked=True)
    response = {"payload": {"devices": [{"id": LOCK_ID, "states": []}]}}

    if source == "push":
        await coordinator.update_push_data(response)
    else:
        mock_uhome_api.get_device_state.return_value = response
        await coordinator._async_update_data()

    assert coordinator.adaptive.is_running(LOCK_ID)
    assert coordinator.adaptive.young_confirmation(LOCK_ID) is None
    assert lock.lock_state == "Unknown"  # real client applies the empty state


async def test_contradicting_poll_after_young_confirmation_is_deferred(
    coordinator, mock_uhome_api
):
    """A stale poll read inside the confirmation window must not undo a lock."""
    lock = await _make_device(mock_uhome_api, locked=False)
    coordinator.devices[LOCK_ID] = lock
    coordinator.start_adaptive_poll(LOCK_ID, expected_locked=True)

    mock_uhome_api.get_device_state.return_value = {
        "payload": {"devices": [_raw_state(locked=True)]}
    }
    await coordinator._async_update_data()  # confirms and stops the burst
    assert not coordinator.adaptive.is_running(LOCK_ID)
    assert coordinator.adaptive.young_confirmation(LOCK_ID) is not None

    mock_uhome_api.get_device_state.return_value = {
        "payload": {"devices": [_raw_state(locked=False)]}
    }
    await coordinator._async_update_data()  # stale contradicting read

    assert lock.lock_state == "Locked"  # contradicting report not applied
    assert coordinator.adaptive.is_running(LOCK_ID)  # burst re-armed
    assert coordinator.adaptive.expected_locked(LOCK_ID) is True


async def test_contradicting_push_after_young_confirmation_is_deferred(coordinator):
    """A stale push inside the confirmation window must not undo a lock."""
    lock = await _make_device(coordinator.api, locked=False)
    coordinator.devices[LOCK_ID] = lock
    coordinator.start_adaptive_poll(LOCK_ID, expected_locked=True)

    await coordinator.update_push_data(
        {"payload": {"devices": [_raw_state(locked=True)]}}
    )
    assert not coordinator.adaptive.is_running(LOCK_ID)
    assert coordinator.adaptive.young_confirmation(LOCK_ID) is not None

    await coordinator.update_push_data(
        {"payload": {"devices": [_raw_state(locked=False)]}}
    )

    assert lock.lock_state == "Locked"  # contradicting report not applied
    assert coordinator.adaptive.is_running(LOCK_ID)  # burst re-armed
    assert coordinator.adaptive.expected_locked(LOCK_ID) is True


async def test_push_excluded_device_keeps_polling_until_confirming_api_read(
    coordinator, mock_uhome_api
):
    """An excluded push cannot confirm stale cache; an allowed API read can."""
    lock = await _make_device(coordinator.api, locked=False)
    coordinator.devices[LOCK_ID] = lock
    coordinator.push_devices = ["other-lock"]  # LOCK_ID is not selected
    coordinator.start_adaptive_poll(LOCK_ID, expected_locked=True)
    assert coordinator.adaptive.is_running(LOCK_ID)

    await coordinator.update_push_data(
        {"payload": {"devices": [_raw_state(locked=True)]}}
    )

    assert coordinator.adaptive.is_running(LOCK_ID)
    assert coordinator.adaptive.expected_locked(LOCK_ID) is True
    assert coordinator.adaptive.young_confirmation(LOCK_ID) is None
    assert lock.lock_state == "Unlocked"  # excluded: payload not applied

    mock_uhome_api.get_device_state.return_value = {
        "payload": {"devices": [_raw_state(locked=True)]}
    }
    # Fire the scheduled callback so its timer is consumed before confirmation.
    async_fire_time_changed(
        coordinator.hass, dt_util.utcnow() + timedelta(seconds=2)
    )
    await coordinator.hass.async_block_till_done()

    mock_uhome_api.get_device_state.assert_awaited_once_with([LOCK_ID], None)
    assert lock.lock_state == "Locked"
    assert coordinator.adaptive.young_confirmation(LOCK_ID)["locked"] is True
    assert not coordinator.adaptive.is_running(LOCK_ID)
