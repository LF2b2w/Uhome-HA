"""Tests for UhomeSwitchEntity."""

from unittest.mock import MagicMock, patch

import pytest

from custom_components.u_tec.const import CONF_OPTIMISTIC_SWITCHES, DOMAIN, SIGNAL_DEVICE_UPDATE
from custom_components.u_tec.switch import UhomeSwitchEntity
from tests.common import make_config_entry, make_fake_lock, make_fake_switch


@pytest.fixture
def coord_with_switch(hass):
    entry = make_config_entry(options={CONF_OPTIMISTIC_SWITCHES: True})
    entry.add_to_hass(hass)
    sw = make_fake_switch("sw-1", is_on=False)
    coord = MagicMock()
    coord.devices = {"sw-1": sw}
    coord.config_entry = entry
    coord.last_update_success = True
    coord.data = {}
    return coord, sw


def test_init_sets_unique_id(coord_with_switch):
    coord, sw = coord_with_switch
    ent = UhomeSwitchEntity(coord, "sw-1")
    assert ent.unique_id == f"{DOMAIN}_sw-1"


async def test_turn_on_sets_optimistic(coord_with_switch, hass):
    coord, sw = coord_with_switch
    ent = UhomeSwitchEntity(coord, "sw-1")
    ent.hass = hass
    ent.entity_id = "switch.fake_switch"
    ent.async_write_ha_state = MagicMock()

    await ent.async_turn_on()

    sw.turn_on.assert_awaited_once()
    assert ent._optimistic_is_on is True


async def test_turn_off_sets_optimistic(coord_with_switch, hass):
    coord, sw = coord_with_switch
    ent = UhomeSwitchEntity(coord, "sw-1")
    ent.hass = hass
    ent.entity_id = "switch.fake_switch"
    ent.async_write_ha_state = MagicMock()

    await ent.async_turn_off()

    sw.turn_off.assert_awaited_once()
    assert ent._optimistic_is_on is False


async def test_coordinator_update_clears_optimistic_on_confirm(coord_with_switch, hass):
    coord, sw = coord_with_switch
    ent = UhomeSwitchEntity(coord, "sw-1")
    ent.hass = hass
    ent.async_write_ha_state = MagicMock()
    ent._optimistic_is_on = True
    sw.is_on = True

    ent._handle_coordinator_update()

    assert ent._optimistic_is_on is None


async def test_turn_on_wraps_device_error(coord_with_switch, hass):
    from homeassistant.exceptions import HomeAssistantError
    from utec_py.exceptions import DeviceError

    coord, sw = coord_with_switch
    sw.turn_on.side_effect = DeviceError("nope")
    ent = UhomeSwitchEntity(coord, "sw-1")
    ent.hass = hass
    ent.entity_id = "switch.fake_switch"

    with pytest.raises(HomeAssistantError):
        await ent.async_turn_on()


async def test_assumed_state_respects_optimistic_config(hass):
    entry = make_config_entry(options={CONF_OPTIMISTIC_SWITCHES: False})
    entry.add_to_hass(hass)
    sw = make_fake_switch("sw-1")
    coord = MagicMock()
    coord.devices = {"sw-1": sw}
    coord.config_entry = entry
    coord.last_update_success = True

    ent = UhomeSwitchEntity(coord, "sw-1")
    ent._optimistic_is_on = True
    assert ent.assumed_state is False


# --- async_setup_entry isinstance filter ---


async def test_setup_entry_filters_non_switch_devices(hass):
    """Coordinator with mixed devices; only UhomeSwitch instances become entities."""
    from custom_components.u_tec.switch import async_setup_entry

    entry = make_config_entry()
    entry.add_to_hass(hass)

    sw = make_fake_switch("sw-1")
    lock = make_fake_lock("lock-1")

    coord = MagicMock()
    coord.devices = {"sw-1": sw, "lock-1": lock}
    coord.config_entry = entry
    coord.last_update_success = True
    coord.data = {}

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {"coordinator": coord}

    added = []

    def fake_add(entities, **kwargs):
        added.extend(list(entities))

    await async_setup_entry(hass, entry, fake_add)

    assert len(added) == 1
    assert added[0]._device.device_id == "sw-1"


# --- available returns False when last_update_success=False ---


def test_available_false_when_coordinator_failed(hass):
    """coordinator.last_update_success=False → available is False."""
    entry = make_config_entry()
    entry.add_to_hass(hass)
    sw = make_fake_switch("sw-1", available=True)
    coord = MagicMock()
    coord.devices = {"sw-1": sw}
    coord.config_entry = entry
    coord.last_update_success = False

    ent = UhomeSwitchEntity(coord, "sw-1")
    assert ent.available is False


# --- is_on returns optimistic value when set; falls back to device ---


def test_is_on_returns_optimistic_when_set(coord_with_switch):
    """_optimistic_is_on set → returns optimistic; cleared → device value."""
    coord, sw = coord_with_switch
    sw.is_on = False
    ent = UhomeSwitchEntity(coord, "sw-1")

    ent._optimistic_is_on = True
    assert ent.is_on is True

    ent._optimistic_is_on = None
    assert ent.is_on is False


# --- assumed_state branches ---


def test_assumed_state_true_when_optimistic_set(coord_with_switch):
    """optimistic enabled + _optimistic_is_on set → assumed_state True."""
    coord, sw = coord_with_switch
    ent = UhomeSwitchEntity(coord, "sw-1")
    ent._optimistic_is_on = True
    assert ent.assumed_state is True


def test_assumed_state_false_when_optimistic_cleared(coord_with_switch):
    """optimistic enabled but _optimistic_is_on=None → assumed_state False."""
    coord, sw = coord_with_switch
    ent = UhomeSwitchEntity(coord, "sw-1")
    ent._optimistic_is_on = None
    assert ent.assumed_state is False


# --- turn_on non-optimistic path (no optimistic write when _is_optimistic False) ---


async def test_turn_on_no_optimistic_when_disabled(hass):
    """_is_optimistic() False → turn_on succeeds, _optimistic_is_on stays None."""
    entry = make_config_entry(options={CONF_OPTIMISTIC_SWITCHES: False})
    entry.add_to_hass(hass)
    sw = make_fake_switch("sw-1")
    coord = MagicMock()
    coord.devices = {"sw-1": sw}
    coord.config_entry = entry
    coord.last_update_success = True

    ent = UhomeSwitchEntity(coord, "sw-1")
    ent.hass = hass
    ent.entity_id = "switch.fake_switch"
    ent.async_write_ha_state = MagicMock()

    await ent.async_turn_on()

    sw.turn_on.assert_awaited_once()
    assert ent._optimistic_is_on is None
    ent.async_write_ha_state.assert_not_called()


# --- turn_off non-optimistic path ---


async def test_turn_off_no_optimistic_when_disabled(hass):
    """_is_optimistic() False → turn_off succeeds, _optimistic_is_on stays None."""
    entry = make_config_entry(options={CONF_OPTIMISTIC_SWITCHES: False})
    entry.add_to_hass(hass)
    sw = make_fake_switch("sw-1")
    coord = MagicMock()
    coord.devices = {"sw-1": sw}
    coord.config_entry = entry
    coord.last_update_success = True

    ent = UhomeSwitchEntity(coord, "sw-1")
    ent.hass = hass
    ent.entity_id = "switch.fake_switch"
    ent.async_write_ha_state = MagicMock()

    await ent.async_turn_off()

    sw.turn_off.assert_awaited_once()
    assert ent._optimistic_is_on is None
    ent.async_write_ha_state.assert_not_called()


# --- turn_on DeviceError → logs + raises HomeAssistantError ---


async def test_turn_on_device_error_logs_and_raises(coord_with_switch, hass):
    """turn_on raises DeviceError → diagnostic logged + HomeAssistantError."""
    from homeassistant.exceptions import HomeAssistantError
    from utec_py.exceptions import DeviceError

    coord, sw = coord_with_switch
    sw.turn_on.side_effect = DeviceError("hw fault")

    ent = UhomeSwitchEntity(coord, "sw-1")
    ent.hass = hass
    ent.entity_id = "switch.fake_switch"
    ent.async_write_ha_state = MagicMock()

    with patch("custom_components.u_tec.switch._LOGGER") as mock_logger:
        with pytest.raises(HomeAssistantError, match="Failed to turn on switch"):
            await ent.async_turn_on()
        # A diagnostic is emitted, but don't couple to a specific log level.
        assert any(
            getattr(mock_logger, level).called
            for level in ("error", "warning", "exception", "critical")
        )

    assert ent._optimistic_is_on is None


# --- turn_off DeviceError → logs + raises HomeAssistantError ---


async def test_turn_off_device_error_logs_and_raises(coord_with_switch, hass):
    """turn_off raises DeviceError → diagnostic logged + HomeAssistantError."""
    from homeassistant.exceptions import HomeAssistantError
    from utec_py.exceptions import DeviceError

    coord, sw = coord_with_switch
    sw.turn_off.side_effect = DeviceError("hw fault")

    ent = UhomeSwitchEntity(coord, "sw-1")
    ent.hass = hass
    ent.entity_id = "switch.fake_switch"
    ent.async_write_ha_state = MagicMock()

    with patch("custom_components.u_tec.switch._LOGGER") as mock_logger:
        with pytest.raises(HomeAssistantError, match="Failed to turn off switch"):
            await ent.async_turn_off()
        assert any(
            getattr(mock_logger, level).called
            for level in ("error", "warning", "exception", "critical")
        )

    assert ent._optimistic_is_on is None


# --- async_added_to_hass registers dispatcher connection ---


async def test_async_added_to_hass_registers_dispatcher(coord_with_switch, hass):
    """async_added_to_hass connects dispatcher for SIGNAL_DEVICE_UPDATE_{device_id}."""
    coord, sw = coord_with_switch
    ent = UhomeSwitchEntity(coord, "sw-1")
    ent.hass = hass
    ent.entity_id = "switch.fake_switch"
    ent.async_write_ha_state = MagicMock()

    with patch(
        "custom_components.u_tec.switch.async_dispatcher_connect",
        return_value=lambda: None,
    ) as mock_connect:
        ent.async_on_remove = MagicMock()
        await ent.async_added_to_hass()

    mock_connect.assert_called_once()
    call_args = mock_connect.call_args
    signal = call_args[0][1]
    assert signal == f"{SIGNAL_DEVICE_UPDATE}_sw-1"
