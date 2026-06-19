"""Tests for UhomeBatterySensorEntity and dynamic addition."""

from unittest.mock import MagicMock

import pytest

from custom_components.u_tec.const import DOMAIN, SIGNAL_NEW_DEVICE
from custom_components.u_tec.sensor import UhomeBatterySensorEntity
from tests.common import make_config_entry, make_fake_lock


@pytest.fixture
def coord_with_locks(hass):
    entry = make_config_entry()
    entry.add_to_hass(hass)
    lock1 = make_fake_lock("lock-1", battery_level=85)
    lock2 = make_fake_lock("lock-2", battery_level=20)
    coord = MagicMock()
    coord.devices = {"lock-1": lock1, "lock-2": lock2}
    coord.config_entry = entry
    coord.last_update_success = True
    coord.added_sensor_entities = set()
    return coord, entry


def test_battery_sensor_exposes_level(coord_with_locks):
    coord, _ = coord_with_locks
    ent = UhomeBatterySensorEntity(coord, "lock-1")
    assert ent.native_value == 85


def test_battery_sensor_unique_id(coord_with_locks):
    coord, _ = coord_with_locks
    ent = UhomeBatterySensorEntity(coord, "lock-1")
    assert "lock-1" in ent.unique_id
    assert "battery" in ent.unique_id.lower()


async def test_async_setup_entry_adds_one_per_lock(hass, coord_with_locks):
    """Initial setup should add battery sensors for all locks plus one last-push sensor."""
    from custom_components.u_tec.sensor import UhomeBatterySensorEntity, async_setup_entry

    coord, entry = coord_with_locks
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {"coordinator": coord}
    added = []

    def _add(entities):
        added.extend(list(entities))

    await async_setup_entry(hass, entry, _add)
    battery_sensors = [e for e in added if isinstance(e, UhomeBatterySensorEntity)]
    assert len(battery_sensors) == 2
    assert len(added) == 3  # 2 battery + 1 last-push
    assert coord.added_sensor_entities == {"u_tec_battery_lock-1", "u_tec_battery_lock-2"}


async def test_async_setup_entry_dispatch_adds_new_devices(hass, coord_with_locks):
    """SIGNAL_NEW_DEVICE dispatch should add sensors for newly-discovered locks."""
    from homeassistant.helpers.dispatcher import async_dispatcher_send

    from custom_components.u_tec.sensor import async_setup_entry

    coord, entry = coord_with_locks
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {"coordinator": coord}
    added = []

    def _add(entities):
        added.extend(list(entities))

    await async_setup_entry(hass, entry, _add)
    initial_count = len(added)

    # Add a new lock, then dispatch
    coord.devices["lock-3"] = make_fake_lock("lock-3", battery_level=50)
    async_dispatcher_send(hass, SIGNAL_NEW_DEVICE)
    await hass.async_block_till_done()

    assert len(added) == initial_count + 1
    assert "u_tec_battery_lock-3" in coord.added_sensor_entities


async def test_dispatch_does_not_double_add(hass, coord_with_locks):
    from homeassistant.helpers.dispatcher import async_dispatcher_send

    from custom_components.u_tec.sensor import async_setup_entry

    coord, entry = coord_with_locks
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {"coordinator": coord}
    added = []

    def _add(entities):
        added.extend(list(entities))

    await async_setup_entry(hass, entry, _add)
    initial = len(added)

    async_dispatcher_send(hass, SIGNAL_NEW_DEVICE)
    await hass.async_block_till_done()

    # Same devices -> no additions
    assert len(added) == initial


async def test_last_push_sensor_added_once(hass, coord_with_locks):
    """async_setup_entry adds exactly one coordinator-level last-push sensor."""
    from custom_components.u_tec.sensor import UhomeLastPushSensor, async_setup_entry

    coord, entry = coord_with_locks
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {"coordinator": coord}
    added = []
    await async_setup_entry(hass, entry, lambda ents: added.extend(list(ents)))

    last_push = [e for e in added if isinstance(e, UhomeLastPushSensor)]
    assert len(last_push) == 1


async def test_last_push_sensor_native_value_and_class(hass, coord_with_locks):
    """The sensor reports the coordinator's last_push_received as a timestamp."""
    from homeassistant.components.sensor import SensorDeviceClass
    from homeassistant.util import dt as dt_util

    from custom_components.u_tec.sensor import UhomeLastPushSensor

    coord, _ = coord_with_locks
    coord.last_push_received = None
    sensor = UhomeLastPushSensor(coord)
    assert sensor.device_class == SensorDeviceClass.TIMESTAMP

    assert sensor.native_value is None  # no push yet
    stamp = dt_util.utcnow()
    coord.last_push_received = stamp
    assert sensor.native_value == stamp
