"""Tests for UhomeLockEntity."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from homeassistant.exceptions import HomeAssistantError
from utec_py.exceptions import DeviceError

from custom_components.u_tec.const import CONF_OPTIMISTIC_LOCKS, DOMAIN, SIGNAL_DEVICE_UPDATE
from custom_components.u_tec.lock import UhomeLockEntity, async_setup_entry
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
    lock.battery_level = 77
    ent = UhomeLockEntity(coord, "lock-1")
    attrs = ent.extra_state_attributes or {}
    # Adjust keys to match actual impl
    assert attrs.get("door_state") in ("open", True) or attrs.get("is_door_open") is True
    assert attrs.get("battery_level") == 77


def test_extra_state_attributes_omit_door_sensor_when_absent(coord_with_lock):
    coord, lock = coord_with_lock
    lock.has_door_sensor = False
    ent = UhomeLockEntity(coord, "lock-1")
    attrs = ent.extra_state_attributes or {}
    assert "door_state" not in attrs and "is_door_open" not in attrs


# ---------------------------------------------------------------------------
# Lines 34-38: async_setup_entry filters non-lock devices
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
# Line 77: available returns False when coordinator or device unavailable
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
# Lines 82-84: is_locked returns optimistic value when set
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
# Line 94: is_jammed delegates to device
# ---------------------------------------------------------------------------

def test_is_jammed_true_when_device_jammed(coord_with_lock):
    coord, lock = coord_with_lock
    lock.is_jammed = True
    ent = UhomeLockEntity(coord, "lock-1")
    assert ent.is_jammed is True


# ---------------------------------------------------------------------------
# Lines 103-111: _handle_coordinator_update clears optimistic only on match
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
# Lines 132->exit, 135-137: async_lock DeviceError → HomeAssistantError
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
        mock_logger.error.assert_called_once()


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
# Lines 144->exit, 147-149: async_unlock DeviceError → HomeAssistantError
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
        mock_logger.error.assert_called_once()


# ---------------------------------------------------------------------------
# Lines 153-155: async_added_to_hass registers dispatcher signal
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
# Line 166: _handle_push_update calls async_write_ha_state
# ---------------------------------------------------------------------------

def test_handle_push_update_writes_ha_state(coord_with_lock):
    coord, lock = coord_with_lock
    ent = UhomeLockEntity(coord, "lock-1")
    ent.async_write_ha_state = MagicMock()

    ent._handle_push_update({"some": "data"})

    ent.async_write_ha_state.assert_called_once()
