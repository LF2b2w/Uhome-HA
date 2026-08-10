"""Tests for entity availability (device offline + consecutive poll failures)."""

from unittest.mock import MagicMock

from custom_components.u_tec.const import (
    CONF_OPTIMISTIC_LOCKS,
    DOMAIN,
    MAX_CONSECUTIVE_UPDATE_FAILURES,
)
from custom_components.u_tec.lock import UhomeLockEntity
from tests.common import make_config_entry, make_fake_lock


def _coord_with_lock():
    entry = make_config_entry(options={CONF_OPTIMISTIC_LOCKS: True})
    lock = make_fake_lock("lock-1", is_locked=True)
    lock.available = True
    coord = MagicMock()
    coord.devices = {"lock-1": lock}
    coord.config_entry = entry
    coord.last_update_success = True
    coord.consecutive_update_failures = 0
    coord.poll_healthy_enough = True
    coord.data = {}
    return coord, lock


def test_available_when_healthy():
    coord, lock = _coord_with_lock()
    ent = UhomeLockEntity(coord, "lock-1")
    assert ent.available is True


def test_available_through_single_poll_failure():
    """One failed poll must not blank the entity."""
    coord, lock = _coord_with_lock()
    coord.consecutive_update_failures = 1
    coord.poll_healthy_enough = (
        coord.consecutive_update_failures < MAX_CONSECUTIVE_UPDATE_FAILURES
    )
    coord.last_update_success = False
    ent = UhomeLockEntity(coord, "lock-1")
    assert ent.available is True


def test_unavailable_after_two_consecutive_poll_failures():
    coord, lock = _coord_with_lock()
    coord.consecutive_update_failures = 2
    coord.poll_healthy_enough = (
        coord.consecutive_update_failures < MAX_CONSECUTIVE_UPDATE_FAILURES
    )
    coord.last_update_success = False
    ent = UhomeLockEntity(coord, "lock-1")
    assert ent.available is False


def test_unavailable_when_device_offline():
    coord, lock = _coord_with_lock()
    lock.available = False
    ent = UhomeLockEntity(coord, "lock-1")
    assert ent.available is False


def test_poll_healthy_enough_property():
    """Coordinator helper mirrors the consecutive-failure threshold."""
    from custom_components.u_tec.coordinator import UhomeDataUpdateCoordinator

    # Exercise the real property without a full HA setup.
    c = object.__new__(UhomeDataUpdateCoordinator)
    c.consecutive_update_failures = 0
    assert c.poll_healthy_enough is True
    c.consecutive_update_failures = 1
    assert c.poll_healthy_enough is True
    c.consecutive_update_failures = 2
    assert c.poll_healthy_enough is False
