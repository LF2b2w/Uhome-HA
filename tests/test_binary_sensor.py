"""Tests for UhomeDoorSensor."""

from unittest.mock import MagicMock

import pytest

from custom_components.u_tec.binary_sensor import UhomeDoorSensor
from tests.common import make_fake_lock


@pytest.fixture
def door_sensor_setup(hass):
    lock = make_fake_lock("lock-1", has_door_sensor=True)
    lock.is_door_closed = True  # closed by default; tests override per case
    coord = MagicMock()
    coord.devices = {"lock-1": lock}
    coord.last_update_success = True
    return coord, lock


def test_is_on_false_when_door_closed(door_sensor_setup):
    coord, lock = door_sensor_setup
    lock.is_door_closed = True
    ent = UhomeDoorSensor(coord, "lock-1")
    assert ent.is_on is False


def test_is_on_true_when_door_open(door_sensor_setup):
    coord, lock = door_sensor_setup
    lock.is_door_closed = False
    ent = UhomeDoorSensor(coord, "lock-1")
    assert ent.is_on is True


def test_available_requires_coordinator_and_device(door_sensor_setup):
    coord, lock = door_sensor_setup
    ent = UhomeDoorSensor(coord, "lock-1")
    assert ent.available is True

    coord.last_update_success = False
    assert ent.available is False


async def test_async_setup_entry_only_adds_locks_with_door_sensor(hass):
    """Locks without `has_door_sensor` should not get a binary sensor."""
    from tests.common import make_config_entry
    from custom_components.u_tec.binary_sensor import async_setup_entry
    from custom_components.u_tec.const import DOMAIN

    entry = make_config_entry()
    entry.add_to_hass(hass)
    lock_with = make_fake_lock("lock-1", has_door_sensor=True)
    lock_without = make_fake_lock("lock-2", has_door_sensor=False)
    coord = MagicMock()
    coord.devices = {"lock-1": lock_with, "lock-2": lock_without}
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {"coordinator": coord}

    added = []

    def _add(entities):
        added.extend(list(entities))

    await async_setup_entry(hass, entry, _add)

    assert len(added) == 1
