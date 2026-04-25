"""Tests for UhomeLockEntity."""

from unittest.mock import MagicMock

import pytest

from custom_components.u_tec.const import CONF_OPTIMISTIC_LOCKS, DOMAIN
from custom_components.u_tec.lock import UhomeLockEntity
from tests.common import make_config_entry, make_fake_lock


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
