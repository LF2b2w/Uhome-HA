"""Regression coverage for unknown lock reports and real HA notifications."""

from datetime import timedelta

import pytest
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.util import dt as dt_util
from utec_client.devices.lock import Lock

from custom_components.u_tec.const import OPTIMISTIC_TIMEOUT
from custom_components.u_tec.coordinator import UhomeDataUpdateCoordinator
from custom_components.u_tec.lock import UhomeLockEntity
from tests.common import make_config_entry

STATE_LOCKED = "locked"
STATE_UNLOCKED = "unlocked"


def make_real_lock():
    """Return a pinned-client Lock with a healthy, unlocked initial report."""
    lock = Lock(
        {
            "id": "lock-1",
            "name": "Test lock",
            "handleType": "utec-lock",
            "category": "lock",
            "deviceInfo": {},
            "attributes": {},
        },
        None,
    )
    lock._state_data = {
        "id": "lock-1",
        "states": [
            {"capability": "st.lock", "name": "lockState", "value": "Unlocked"},
            {"capability": "st.healthCheck", "name": "status", "value": "Online"},
        ],
    }
    return lock


@pytest.fixture(autouse=True)
async def cleanup_entities(hass):
    """Remove manually added entities and their coordinator/dispatcher listeners."""
    entities = []
    hass.data["test_unknown_lock_entities"] = entities
    yield
    for entity in reversed(entities):
        await entity.async_remove()
    await hass.async_block_till_done()


async def add_entity(hass, mock_uhome_api, lock, *, optimistic=False):
    entry = make_config_entry(options={"optimistic_locks": optimistic})
    entry.add_to_hass(hass)
    coordinator = UhomeDataUpdateCoordinator(
        hass,
        mock_uhome_api,
        config_entry=entry,
        scan_interval=10,
        discovery_interval=300,
    )
    coordinator.devices["lock-1"] = lock
    entity = UhomeLockEntity(coordinator, "lock-1")
    entity.hass = hass
    entity.entity_id = "lock.test_lock"
    hass.data["test_unknown_lock_entities"].append(entity)
    await entity.async_added_to_hass()
    entity.async_write_ha_state()
    await hass.async_block_till_done()
    return coordinator, entity


async def test_real_pinned_lock_replaces_state_unknown_and_recovers(
    hass, mock_uhome_api
):
    lock = make_real_lock()
    coordinator, entity = await add_entity(hass, mock_uhome_api, lock)

    for initial in ["Locked", "Unlocked"]:
        # Each sequence begins with a recognized report, then the API replaces
        # it with an explicit unknown value, then a recognized state returns.
        for value, expected in (
            (initial, initial.lower()),
            ("Unknown", STATE_UNKNOWN),
            (initial, initial.lower()),
        ):
            await coordinator.update_push_data(
                {
                    "payload": {
                        "devices": [
                            {
                                "id": "lock-1",
                                "states": [
                                    {
                                        "capability": "st.lock",
                                        "name": "lockState",
                                        "value": value,
                                    },
                                    {
                                        "capability": "st.healthCheck",
                                        "name": "status",
                                        "value": "Online",
                                    },
                                ],
                            }
                        ]
                    }
                }
            )
            await hass.async_block_till_done()
            state = hass.states.get(entity.entity_id)
            assert state is not None and state.state == expected
            assert lock.lock_state == value

        # Also cover absent lock capability through a full replacement push.
        await coordinator.update_push_data(
            {
                "payload": {
                    "devices": [
                        {
                            "id": "lock-1",
                            "states": [
                                {
                                    "capability": "st.healthCheck",
                                    "name": "status",
                                    "value": "Online",
                                }
                            ],
                        }
                    ]
                }
            }
        )
        await hass.async_block_till_done()
        state = hass.states.get(entity.entity_id)
        assert state is not None and state.state == STATE_UNKNOWN
        assert entity.is_locked is None


@pytest.mark.parametrize("position", ["Locked", "Unlocked", "Unknown", None])
async def test_missing_or_offline_health_makes_entity_unavailable(
    hass, mock_uhome_api, position
):
    lock = make_real_lock()
    states = (
        []
        if position is None
        else [{"capability": "st.lock", "name": "lockState", "value": position}]
    )
    if position != "Unknown":
        states.append(
            {"capability": "st.healthCheck", "name": "status", "value": "Offline"}
        )
    # For Unknown, omit health entirely; the other cases explicitly report Offline.
    lock._state_data = {"id": "lock-1", "states": states}
    _, entity = await add_entity(hass, mock_uhome_api, lock)
    state = hass.states.get(entity.entity_id)
    assert state is not None and state.state == STATE_UNAVAILABLE
    assert entity.is_locked is (
        True if position == "Locked" else False if position == "Unlocked" else None
    )


@pytest.mark.parametrize("target", [True, False], ids=["lock-target", "unlock-target"])
@pytest.mark.parametrize(
    ("reported", "should_clear"),
    [("matching", True), ("opposite", True), ("Unknown", False), ("partial", False)],
)
async def test_real_push_listener_confirms_only_definite_position(
    hass, mock_uhome_api, target, reported, should_clear
):
    lock = make_real_lock()
    coordinator, entity = await add_entity(hass, mock_uhome_api, lock, optimistic=True)
    entity._optimistic_is_locked = target
    entity._optimistic_set_at = dt_util.utcnow() - timedelta(seconds=1)
    value = {
        "matching": "Locked" if target else "Unlocked",
        "opposite": "Unlocked" if target else "Locked",
        "Unknown": "Unknown",
    }.get(reported)
    states = (
        []
        if reported == "partial"
        else [{"capability": "st.lock", "name": "lockState", "value": value}]
    )
    states.append({"capability": "st.healthCheck", "name": "status", "value": "Online"})

    await coordinator.update_push_data(
        {"payload": {"devices": [{"id": "lock-1", "states": states}]}}
    )
    await hass.async_block_till_done()

    if should_clear:
        assert entity._optimistic_is_locked is None
        assert entity._optimistic_set_at is None
        expected = (
            STATE_LOCKED
            if reported == "matching" and target
            else (
                STATE_UNLOCKED
                if reported == "matching"
                else STATE_UNLOCKED if target else STATE_LOCKED
            )
        )
        assert hass.states.get(entity.entity_id).state == expected
    else:
        assert entity._optimistic_is_locked is target
        assert entity._optimistic_set_at is not None
        assert entity.assumed_state is True
        assert hass.states.get(entity.entity_id).state == (
            STATE_LOCKED if target else STATE_UNLOCKED
        )


@pytest.mark.parametrize("target", [True, False], ids=["lock-target", "unlock-target"])
@pytest.mark.parametrize("notification", ["ordinary", "adaptive"])
async def test_unknown_confirmation_grace_recovers_repeats_and_expires(
    hass, mock_uhome_api, target, notification
):
    lock = make_real_lock()
    lock._state_data = {
        "id": "lock-1",
        "states": [
            {"capability": "st.lock", "name": "lockState", "value": "Unknown"},
            {"capability": "st.healthCheck", "name": "status", "value": "Online"},
        ],
    }
    coordinator, entity = await add_entity(hass, mock_uhome_api, lock, optimistic=True)
    entity._optimistic_is_locked = target
    entity._optimistic_set_at = None

    def notify():
        if notification == "ordinary":
            coordinator.async_set_updated_data(coordinator.data)
        else:
            entity._handle_adaptive_poll(lock.get_state_data())

    notify()
    await hass.async_block_till_done()
    first_stamp = entity._optimistic_set_at
    assert first_stamp is not None
    assert entity._optimistic_is_locked is target
    assert entity.assumed_state is True

    notify()
    await hass.async_block_till_done()
    assert entity._optimistic_set_at == first_stamp
    assert entity._optimistic_is_locked is target

    entity._optimistic_set_at = (
        dt_util.utcnow() - OPTIMISTIC_TIMEOUT - timedelta(seconds=1)
    )
    notify()
    await hass.async_block_till_done()
    assert entity._optimistic_is_locked is None
    assert entity._optimistic_set_at is None
    state = hass.states.get(entity.entity_id)
    assert state is not None and state.state == STATE_UNKNOWN


async def test_jammed_takes_precedence_over_unknown_position(hass, mock_uhome_api):
    lock = make_real_lock()
    lock._state_data = {
        "id": "lock-1",
        "states": [
            {"capability": "st.lock", "name": "lockState", "value": "Jammed"},
            {"capability": "st.healthCheck", "name": "status", "value": "Online"},
        ],
    }
    _, entity = await add_entity(hass, mock_uhome_api, lock)
    assert entity.is_locked is None
    assert entity.is_jammed is True
    assert lock.lock_state == "Jammed"
    state = hass.states.get(entity.entity_id)
    assert state is not None and state.state == "jammed"
