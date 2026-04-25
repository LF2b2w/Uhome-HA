"""Tests for UhomeSwitchEntity."""

from unittest.mock import MagicMock

import pytest

from custom_components.u_tec.const import CONF_OPTIMISTIC_SWITCHES, DOMAIN
from custom_components.u_tec.switch import UhomeSwitchEntity
from tests.common import make_config_entry, make_fake_switch


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
