"""Tests for UhomeLockEntity."""

from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from homeassistant.const import EVENT_STATE_CHANGED
from homeassistant.exceptions import HomeAssistantError
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import async_capture_events
from utec_py.exceptions import DeviceError

from custom_components.u_tec.const import (
    CONF_OPTIMISTIC_LOCKS,
    DOMAIN,
    OPTIMISTIC_TIMEOUT,
    SIGNAL_DEVICE_UPDATE,
)
from custom_components.u_tec.lock import (
    PASSAGE_MODE,
    UhomeLockEntity,
    async_setup_entry,
)
from tests.common import make_config_entry, make_fake_lock, make_fake_switch


@pytest.fixture
def coord_with_lock(hass):
    entry = make_config_entry(options={CONF_OPTIMISTIC_LOCKS: True})
    entry.add_to_hass(hass)
    lock = make_fake_lock("lock-1", is_locked=True)
    coord = MagicMock()
    coord.devices = {"lock-1": lock}
    coord.config_entry = entry
    coord.last_update_success = True
    coord.data = {}
    return coord, lock


def test_init_unique_id(coord_with_lock):
    coord, lock = coord_with_lock
    ent = UhomeLockEntity(coord, "lock-1")
    assert ent.unique_id == f"{DOMAIN}_lock-1"


async def test_async_lock_sets_optimistic(coord_with_lock, hass):
    coord, lock = coord_with_lock
    lock.is_locked = False  # starting from unlocked
    ent = UhomeLockEntity(coord, "lock-1")
    ent.hass = hass
    ent.entity_id = "lock.fake_lock"
    ent.async_write_ha_state = MagicMock()

    await ent.async_lock()

    lock.lock.assert_awaited_once()


async def test_async_unlock_calls_device(coord_with_lock, hass):
    coord, lock = coord_with_lock
    ent = UhomeLockEntity(coord, "lock-1")
    ent.hass = hass
    ent.entity_id = "lock.fake_lock"
    ent.async_write_ha_state = MagicMock()

    await ent.async_unlock()

    lock.unlock.assert_awaited_once()


def test_is_jammed_reflects_device(coord_with_lock):
    coord, lock = coord_with_lock
    lock.is_jammed = True
    ent = UhomeLockEntity(coord, "lock-1")
    assert ent.is_jammed is True


def test_extra_state_attributes_include_door_sensor_when_present(coord_with_lock):
    coord, lock = coord_with_lock
    lock.has_door_sensor = True
    lock.is_door_open = True
    lock.door_state = "open"
    lock.battery_level = 77
    ent = UhomeLockEntity(coord, "lock-1")
    attrs = ent.extra_state_attributes or {}
    assert attrs["door_state"] == "open"
    assert attrs["is_door_open"] is True
    assert attrs["battery_level"] == 77


def test_extra_state_attributes_omit_door_sensor_when_absent(coord_with_lock):
    coord, lock = coord_with_lock
    lock.has_door_sensor = False
    ent = UhomeLockEntity(coord, "lock-1")
    attrs = ent.extra_state_attributes or {}
    assert "door_state" not in attrs and "is_door_open" not in attrs


# ---------------------------------------------------------------------------
# async_setup_entry filters non-lock devices
# ---------------------------------------------------------------------------

async def test_setup_entry_excludes_non_lock_devices(hass):
    """Non-lock devices in coordinator.devices must NOT produce entities."""
    entry = make_config_entry()
    entry.add_to_hass(hass)

    lock = make_fake_lock("lock-1")
    switch = make_fake_switch("sw-1")

    coord = MagicMock()
    coord.devices = {"lock-1": lock, "sw-1": switch}
    coord.config_entry = entry
    coord.last_update_success = True
    coord.data = {}

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {"coordinator": coord}

    added = []
    async_add_entities = MagicMock(side_effect=lambda ents: added.extend(list(ents)))

    await async_setup_entry(hass, entry, async_add_entities)

    assert len(added) == 1
    assert added[0]._device.device_id == "lock-1"


# ---------------------------------------------------------------------------
# available returns False when coordinator or device unavailable
# ---------------------------------------------------------------------------

def test_available_false_when_coordinator_update_failed(coord_with_lock):
    coord, lock = coord_with_lock
    coord.last_update_success = False
    ent = UhomeLockEntity(coord, "lock-1")
    assert ent.available is False


def test_available_false_when_device_unavailable(coord_with_lock):
    coord, lock = coord_with_lock
    lock.available = False
    ent = UhomeLockEntity(coord, "lock-1")
    assert ent.available is False


# ---------------------------------------------------------------------------
# is_locked returns optimistic value when set
# ---------------------------------------------------------------------------

def test_is_locked_returns_optimistic_when_set(coord_with_lock):
    coord, lock = coord_with_lock
    lock.is_locked = False  # device says unlocked
    ent = UhomeLockEntity(coord, "lock-1")
    ent._optimistic_is_locked = True  # optimistic says locked
    assert ent.is_locked is True


def test_is_locked_returns_device_value_when_no_optimistic(coord_with_lock):
    coord, lock = coord_with_lock
    lock.is_locked = False
    ent = UhomeLockEntity(coord, "lock-1")
    assert ent._optimistic_is_locked is None
    assert ent.is_locked is False


# ---------------------------------------------------------------------------
# is_jammed delegates to device
# ---------------------------------------------------------------------------

def test_is_jammed_true_when_device_jammed(coord_with_lock):
    coord, lock = coord_with_lock
    lock.is_jammed = True
    ent = UhomeLockEntity(coord, "lock-1")
    assert ent.is_jammed is True


# ---------------------------------------------------------------------------
# _handle_coordinator_update clears optimistic only on match
# ---------------------------------------------------------------------------

def test_handle_coordinator_update_keeps_optimistic_when_unconfirmed(coord_with_lock):
    """Optimistic=True but device still says unlocked → keep optimistic."""
    coord, lock = coord_with_lock
    lock.is_locked = False  # device hasn't caught up yet
    ent = UhomeLockEntity(coord, "lock-1")
    ent.hass = MagicMock()
    ent.async_write_ha_state = MagicMock()
    ent._optimistic_is_locked = True

    ent._handle_coordinator_update()

    assert ent._optimistic_is_locked is True


def test_handle_coordinator_update_clears_optimistic_when_confirmed(coord_with_lock):
    """Optimistic=True and device confirms locked → clear optimistic."""
    coord, lock = coord_with_lock
    lock.is_locked = True  # device confirmed
    ent = UhomeLockEntity(coord, "lock-1")
    ent.hass = MagicMock()
    ent.async_write_ha_state = MagicMock()
    ent._optimistic_is_locked = True

    ent._handle_coordinator_update()

    assert ent._optimistic_is_locked is None


def test_handle_coordinator_update_clears_optimistic_unlocked_confirmed(coord_with_lock):
    """Optimistic=False (unlocked) and device confirms unlocked → clear."""
    coord, lock = coord_with_lock
    lock.is_locked = False
    ent = UhomeLockEntity(coord, "lock-1")
    ent.hass = MagicMock()
    ent.async_write_ha_state = MagicMock()
    ent._optimistic_is_locked = False

    ent._handle_coordinator_update()

    assert ent._optimistic_is_locked is None


# ---------------------------------------------------------------------------
# async_lock DeviceError → HomeAssistantError
# ---------------------------------------------------------------------------

async def test_async_lock_device_error_raises_ha_error(coord_with_lock, hass):
    coord, lock = coord_with_lock
    lock.lock = AsyncMock(side_effect=DeviceError("lock failed"))
    ent = UhomeLockEntity(coord, "lock-1")
    ent.hass = hass
    ent.entity_id = "lock.fake_lock"
    ent.async_write_ha_state = MagicMock()

    with pytest.raises(HomeAssistantError, match="Failed to lock"):
        await ent.async_lock()


async def test_async_lock_device_error_logs_error(coord_with_lock, hass):
    coord, lock = coord_with_lock
    lock.lock = AsyncMock(side_effect=DeviceError("boom"))
    ent = UhomeLockEntity(coord, "lock-1")
    ent.hass = hass
    ent.entity_id = "lock.fake_lock"
    ent.async_write_ha_state = MagicMock()

    with patch("custom_components.u_tec.lock._LOGGER") as mock_logger:
        with pytest.raises(HomeAssistantError):
            await ent.async_lock()
        # A diagnostic is emitted; don't couple to a specific log level.
        assert any(
            getattr(mock_logger, level).called
            for level in ("error", "warning", "exception", "critical")
        )


async def test_async_lock_error_does_not_set_optimistic(coord_with_lock, hass):
    """On DeviceError, _optimistic_is_locked must NOT be written."""
    coord, lock = coord_with_lock
    lock.lock = AsyncMock(side_effect=DeviceError("fail"))
    ent = UhomeLockEntity(coord, "lock-1")
    ent.hass = hass
    ent.entity_id = "lock.fake_lock"
    ent.async_write_ha_state = MagicMock()

    with pytest.raises(HomeAssistantError):
        await ent.async_lock()

    assert ent._optimistic_is_locked is None


# ---------------------------------------------------------------------------
# async_unlock DeviceError → HomeAssistantError
# ---------------------------------------------------------------------------

async def test_async_unlock_device_error_raises_ha_error(coord_with_lock, hass):
    coord, lock = coord_with_lock
    lock.unlock = AsyncMock(side_effect=DeviceError("unlock failed"))
    ent = UhomeLockEntity(coord, "lock-1")
    ent.hass = hass
    ent.entity_id = "lock.fake_lock"
    ent.async_write_ha_state = MagicMock()

    with pytest.raises(HomeAssistantError, match="Failed to unlock"):
        await ent.async_unlock()


async def test_async_unlock_device_error_logs_error(coord_with_lock, hass):
    coord, lock = coord_with_lock
    lock.unlock = AsyncMock(side_effect=DeviceError("boom"))
    ent = UhomeLockEntity(coord, "lock-1")
    ent.hass = hass
    ent.entity_id = "lock.fake_lock"
    ent.async_write_ha_state = MagicMock()

    with patch("custom_components.u_tec.lock._LOGGER") as mock_logger:
        with pytest.raises(HomeAssistantError):
            await ent.async_unlock()
        assert any(
            getattr(mock_logger, level).called
            for level in ("error", "warning", "exception", "critical")
        )


# ---------------------------------------------------------------------------
# async_added_to_hass registers dispatcher signal
# ---------------------------------------------------------------------------

async def test_async_added_to_hass_registers_dispatcher(coord_with_lock, hass):
    coord, lock = coord_with_lock
    ent = UhomeLockEntity(coord, "lock-1")
    ent.hass = hass
    ent.entity_id = "lock.fake_lock"
    ent.async_write_ha_state = MagicMock()
    ent.async_on_remove = MagicMock()

    expected_signal = f"{SIGNAL_DEVICE_UPDATE}_{lock.device_id}"

    with patch("custom_components.u_tec.lock.async_dispatcher_connect") as mock_connect:
        mock_connect.return_value = MagicMock()
        await ent.async_added_to_hass()

    mock_connect.assert_called_once()
    call_args = mock_connect.call_args
    assert call_args[0][1] == expected_signal


# ---------------------------------------------------------------------------
# _handle_push_update calls async_write_ha_state
# ---------------------------------------------------------------------------

def test_handle_push_update_writes_ha_state(coord_with_lock):
    coord, lock = coord_with_lock
    ent = UhomeLockEntity(coord, "lock-1")
    ent.async_write_ha_state = MagicMock()

    ent._handle_push_update({"some": "data"})

    ent.async_write_ha_state.assert_called_once()


# A push payload carrying real lock state, as device.get_state_data() produces.
_PUSH_WITH_LOCK = {"st.lock": {"lockState": "Locked"}}
# A partial push that does not carry lock state (e.g. a door-sensor event).
_PUSH_NO_LOCK = {"st.doorSensor": {"doorState": "open"}}


def test_push_disagreement_clears_optimistic_immediately(coord_with_lock):
    """A push that contradicts optimism drops it at once (no 30s wait).

    The #58 case: user unlocked (optimistic=unlocked), auto-lock re-locked the
    device, and the device pushes "locked". The coordinator has already applied
    the push, so _device.is_locked is True.
    """
    coord, lock = coord_with_lock
    ent = UhomeLockEntity(coord, "lock-1")
    ent.async_write_ha_state = MagicMock()
    ent._optimistic_is_locked = False  # user asked for unlocked
    ent._optimistic_set_at = dt_util.utcnow()
    lock.is_locked = True  # push already applied: device says locked

    ent._handle_push_update(_PUSH_WITH_LOCK)

    assert ent._optimistic_is_locked is None
    assert ent._optimistic_set_at is None
    assert ent.is_locked is True  # now reports the pushed truth
    ent.async_write_ha_state.assert_called_once()


def test_partial_push_without_lock_state_does_not_clear(coord_with_lock):
    """A push that omits lock state must NOT clear optimism.

    Pushes are full-state replaces and Lock.is_locked falls back to False when
    the lock capability is absent, so a door-sensor/battery push would read as a
    spurious "unlocked". Optimism must survive it for the confirm/timeout path.
    """
    coord, lock = coord_with_lock
    ent = UhomeLockEntity(coord, "lock-1")
    ent.async_write_ha_state = MagicMock()
    ent._optimistic_is_locked = True  # user asked for locked
    stamp = dt_util.utcnow()
    ent._optimistic_set_at = stamp
    lock.is_locked = False  # fallback False: capability was wiped by the push

    ent._handle_push_update(_PUSH_NO_LOCK)

    assert ent._optimistic_is_locked is True  # preserved
    assert ent._optimistic_set_at == stamp
    ent.async_write_ha_state.assert_called_once()


def test_push_agreement_keeps_optimistic(coord_with_lock):
    """A push that agrees with optimism leaves it for the confirm/timeout path."""
    coord, lock = coord_with_lock
    ent = UhomeLockEntity(coord, "lock-1")
    ent.async_write_ha_state = MagicMock()
    ent._optimistic_is_locked = True
    stamp = dt_util.utcnow()
    ent._optimistic_set_at = stamp
    lock.is_locked = True  # push agrees

    ent._handle_push_update(_PUSH_WITH_LOCK)

    assert ent._optimistic_is_locked is True
    assert ent._optimistic_set_at == stamp
    ent.async_write_ha_state.assert_called_once()


def test_push_with_no_outstanding_optimism_is_noop_but_writes(coord_with_lock):
    """No optimism outstanding: push just writes, touches nothing."""
    coord, lock = coord_with_lock
    ent = UhomeLockEntity(coord, "lock-1")
    ent.async_write_ha_state = MagicMock()
    assert ent._optimistic_is_locked is None

    ent._handle_push_update(_PUSH_WITH_LOCK)

    assert ent._optimistic_is_locked is None
    ent.async_write_ha_state.assert_called_once()


async def test_async_lock_stamps_optimistic_set_at(coord_with_lock, hass):
    """A command must record when optimism started, so the timeout can bound it."""
    coord, lock = coord_with_lock
    lock.is_locked = False
    ent = UhomeLockEntity(coord, "lock-1")
    ent.hass = hass
    ent.entity_id = "lock.fake_lock"
    ent.async_write_ha_state = MagicMock()

    await ent.async_lock()
    assert ent._optimistic_set_at is not None


async def test_async_unlock_stamps_optimistic_set_at(coord_with_lock, hass):
    coord, lock = coord_with_lock
    lock.is_locked = True
    ent = UhomeLockEntity(coord, "lock-1")
    ent.hass = hass
    ent.entity_id = "lock.fake_lock"
    ent.async_write_ha_state = MagicMock()

    await ent.async_unlock()
    assert ent._optimistic_set_at is not None


def test_confirm_clears_stamp_so_next_command_gets_fresh_clock(coord_with_lock):
    """On confirmation the stamp must clear, or a later un-stamped optimistic
    value would inherit a stale start time and time out prematurely."""
    coord, lock = coord_with_lock
    ent = UhomeLockEntity(coord, "lock-1")
    ent.hass = MagicMock()
    ent.async_write_ha_state = MagicMock()
    ent._optimistic_is_locked = True
    ent._optimistic_set_at = dt_util.utcnow()
    lock.is_locked = True  # device confirms

    ent._handle_coordinator_update()

    assert ent._optimistic_is_locked is None
    assert ent._optimistic_set_at is None


# ---------------------------------------------------------------------------
# Optimistic state must not pin forever when the device never confirms
# ---------------------------------------------------------------------------

async def test_optimistic_clears_once_device_confirms(coord_with_lock, hass):
    """The happy path: optimistic state is released when the device agrees."""
    coord, lock = coord_with_lock
    lock.is_locked = False
    ent = UhomeLockEntity(coord, "lock-1")
    ent.hass = hass
    ent.entity_id = "lock.fake_lock"
    ent.async_write_ha_state = MagicMock()

    await ent.async_lock()
    assert ent.is_locked is True  # optimistic
    assert ent.assumed_state is True

    lock.is_locked = True  # device catches up
    ent._handle_coordinator_update()

    assert ent._optimistic_is_locked is None
    assert ent.is_locked is True
    assert ent.assumed_state is False


async def test_optimistic_times_out_when_device_never_confirms(coord_with_lock, hass):
    """Regression: an unconfirmed optimistic state must not pin forever.

    A lever lock with auto-lock enabled re-locks itself immediately after an
    unlock, so the device never reports "unlocked" and the entity previously
    stayed wrong indefinitely.
    """
    coord, lock = coord_with_lock
    lock.is_locked = True
    ent = UhomeLockEntity(coord, "lock-1")
    ent.hass = hass
    ent.entity_id = "lock.fake_lock"
    ent.async_write_ha_state = MagicMock()

    await ent.async_unlock()
    assert ent.is_locked is False  # optimistic: we asked for unlocked

    # Device never reports unlocked (auto-lock re-locked it).
    ent._handle_coordinator_update()
    assert ent._optimistic_is_locked is False  # still held, within grace

    # Push the stamp beyond the timeout.
    ent._optimistic_set_at = dt_util.utcnow() - (
        OPTIMISTIC_TIMEOUT + timedelta(seconds=1)
    )
    ent._handle_coordinator_update()

    assert ent._optimistic_is_locked is None
    assert ent.is_locked is True  # deferred to the device
    assert ent.assumed_state is False


def test_missing_stamp_starts_the_clock_rather_than_clearing(coord_with_lock):
    """An optimistic value with no timestamp must not be dropped on sight.

    Clearing immediately would destroy the grace period that lets a slow bolt
    finish moving. Start the clock instead, so the timeout still bounds it.
    """
    coord, lock = coord_with_lock
    lock.is_locked = True
    ent = UhomeLockEntity(coord, "lock-1")
    ent.hass = MagicMock()
    ent.async_write_ha_state = MagicMock()
    ent._optimistic_is_locked = False
    ent._optimistic_set_at = None

    ent._handle_coordinator_update()

    assert ent._optimistic_is_locked is False, "optimistic value must be held"
    assert ent._optimistic_set_at is not None, "clock must have been started"

    # It must still time out from that stamp.
    ent._optimistic_set_at = dt_util.utcnow() - (
        OPTIMISTIC_TIMEOUT + timedelta(seconds=1)
    )
    ent._handle_coordinator_update()
    assert ent._optimistic_is_locked is None


# ---------------------------------------------------------------------------
# Passage mode ignores lock commands, so optimism there is always wrong
# ---------------------------------------------------------------------------

def test_is_optimistic_false_in_passage_mode(coord_with_lock):
    coord, lock = coord_with_lock
    lock.lock_mode = PASSAGE_MODE
    ent = UhomeLockEntity(coord, "lock-1")

    assert ent._is_optimistic() is False


def test_is_optimistic_true_in_normal_mode(coord_with_lock):
    coord, lock = coord_with_lock
    lock.lock_mode = "Normal"
    ent = UhomeLockEntity(coord, "lock-1")

    assert ent._is_optimistic() is True


def test_is_optimistic_unaffected_by_unknown_lock_mode(coord_with_lock):
    """utec_py returns None when lockMode is missing or unmapped; fail open."""
    coord, lock = coord_with_lock
    lock.lock_mode = None
    ent = UhomeLockEntity(coord, "lock-1")

    assert ent._is_optimistic() is True


async def test_passage_mode_lock_does_not_set_optimistic(coord_with_lock, hass):
    coord, lock = coord_with_lock
    lock.lock_mode = PASSAGE_MODE
    lock.is_locked = False
    ent = UhomeLockEntity(coord, "lock-1")
    ent.hass = hass
    ent.entity_id = "lock.fake_lock"
    ent.async_write_ha_state = MagicMock()

    await ent.async_lock()

    lock.lock.assert_awaited_once()
    assert ent._optimistic_is_locked is None
    assert ent.is_locked is False  # the truth: passage mode did not lock


def test_entering_passage_mode_drops_outstanding_optimism(coord_with_lock):
    """Optimism from before the mode changed must not survive into Passage.

    _is_optimistic() reports False in Passage, so a retained optimistic value
    would make is_locked return an assumed value while assumed_state claims it
    is confirmed.
    """
    coord, lock = coord_with_lock
    lock.is_locked = True
    lock.lock_mode = "Normal"
    ent = UhomeLockEntity(coord, "lock-1")
    ent.hass = MagicMock()
    ent.async_write_ha_state = MagicMock()
    ent._optimistic_is_locked = False  # user asked for unlocked
    ent._optimistic_set_at = dt_util.utcnow()

    # Device flips to Passage before confirming.
    lock.lock_mode = PASSAGE_MODE
    ent._handle_coordinator_update()

    assert ent._optimistic_is_locked is None
    assert ent.is_locked is True  # device truth
    assert ent.assumed_state is False


# ---------------------------------------------------------------------------
# Passage-mode lock commands must still notify listeners (HomeKit resync)
# ---------------------------------------------------------------------------

async def test_passage_mode_lock_resyncs_listeners(coord_with_lock, hass):
    """A passage-mode lock command changes nothing, so nothing would notify
    listeners. HA's HomeKit bridge only recomputes its target characteristic
    on a state event, so without one the tile hangs on "Locking...".
    Re-assert the unchanged state with force_update so an event still fires.
    """
    coord, lock = coord_with_lock
    lock.lock_mode = PASSAGE_MODE
    lock.is_locked = False
    ent = UhomeLockEntity(coord, "lock-1")
    ent.hass = hass
    ent.entity_id = "lock.fake_lock"

    seen_force = []
    ent.async_write_ha_state = MagicMock(
        side_effect=lambda: seen_force.append(ent.force_update)
    )

    await ent.async_lock()

    ent.async_write_ha_state.assert_called_once()
    assert seen_force == [True], "state must be written with force_update set"
    assert ent.force_update is False, "force_update must be reset after the write"


async def test_normal_mode_lock_does_not_force_update(coord_with_lock, hass):
    """Normal mode already produces a real state change; no forcing needed."""
    coord, lock = coord_with_lock
    lock.lock_mode = "Normal"
    lock.is_locked = False
    ent = UhomeLockEntity(coord, "lock-1")
    ent.hass = hass
    ent.entity_id = "lock.fake_lock"

    seen_force = []
    ent.async_write_ha_state = MagicMock(
        side_effect=lambda: seen_force.append(ent.force_update)
    )

    await ent.async_lock()

    assert seen_force == [False]


async def test_force_update_reset_even_if_write_raises(coord_with_lock, hass):
    """force_update must not leak on if the write blows up."""
    coord, lock = coord_with_lock
    lock.lock_mode = PASSAGE_MODE
    ent = UhomeLockEntity(coord, "lock-1")
    ent.hass = hass
    ent.entity_id = "lock.fake_lock"
    ent.async_write_ha_state = MagicMock(side_effect=RuntimeError("boom"))

    with pytest.raises(RuntimeError):
        await ent.async_lock()

    assert ent.force_update is False


async def test_passage_mode_lock_emits_real_state_event(coord_with_lock, hass):
    """Integration-level: the forced write must reach the state machine.

    The unit tests above mock async_write_ha_state, so they only prove the
    force_update choreography. This one drives the real state machine and
    asserts a state_changed event actually fires for an identical state --
    the property the HomeKit resync depends on.
    """
    coord, lock = coord_with_lock
    lock.lock_mode = PASSAGE_MODE
    lock.is_locked = False
    ent = UhomeLockEntity(coord, "lock-1")
    ent.hass = hass
    ent.entity_id = "lock.fake_lock"

    # Seed the machine with this entity's own state and attributes, so the
    # write under test is byte-identical and would normally be suppressed.
    ent.async_write_ha_state()
    await hass.async_block_till_done()
    before = hass.states.get("lock.fake_lock")
    assert before is not None

    events = async_capture_events(hass, EVENT_STATE_CHANGED)

    await ent.async_lock()
    await hass.async_block_till_done()

    matching = [e for e in events if e.data["entity_id"] == "lock.fake_lock"]
    assert matching, "an identical state must still emit state_changed when forced"
    assert matching[0].data["new_state"].state == before.state
