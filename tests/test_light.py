"""Tests for UhomeLightEntity — init and commands."""

from unittest.mock import MagicMock

import pytest

from custom_components.u_tec.const import CONF_OPTIMISTIC_LIGHTS, DOMAIN
from custom_components.u_tec.light import UhomeLightEntity
from tests.common import make_config_entry, make_fake_light


@pytest.fixture
def coord_with_light(hass):
    entry = make_config_entry(options={CONF_OPTIMISTIC_LIGHTS: True})
    entry.add_to_hass(hass)
    light = make_fake_light("light-1", is_on=False)
    coord = MagicMock()
    coord.devices = {"light-1": light}
    coord.config_entry = entry
    coord.last_update_success = True
    coord.data = {}
    return coord, light


def test_init_sets_unique_id_and_name(coord_with_light):
    coord, light = coord_with_light
    ent = UhomeLightEntity(coord, "light-1")
    assert ent.unique_id == f"{DOMAIN}_light-1"
    assert ent.name == "Fake Light"


def test_is_on_reads_device_when_no_optimistic(coord_with_light):
    coord, light = coord_with_light
    light.is_on = True
    ent = UhomeLightEntity(coord, "light-1")
    assert ent.is_on is True


async def test_async_turn_on_sets_optimistic_and_calls_device(coord_with_light, hass):
    coord, light = coord_with_light
    ent = UhomeLightEntity(coord, "light-1")
    ent.hass = hass
    ent.entity_id = "light.fake_light"
    ent.async_write_ha_state = MagicMock()

    await ent.async_turn_on()

    light.turn_on.assert_awaited_once()
    assert ent._optimistic_is_on is True


async def test_async_turn_off_sets_optimistic_and_calls_device(coord_with_light, hass):
    coord, light = coord_with_light
    light.is_on = True
    ent = UhomeLightEntity(coord, "light-1")
    ent.hass = hass
    ent.entity_id = "light.fake_light"
    ent.async_write_ha_state = MagicMock()

    await ent.async_turn_off()

    light.turn_off.assert_awaited_once()
    assert ent._optimistic_is_on is False


async def test_turn_on_with_brightness_sets_pending(coord_with_light, hass):
    coord, light = coord_with_light
    ent = UhomeLightEntity(coord, "light-1")
    ent.hass = hass
    ent.entity_id = "light.fake_light"
    ent.async_write_ha_state = MagicMock()

    await ent.async_turn_on(brightness=255)  # HA scale 0-255

    light.turn_on.assert_awaited_once()
    _, call_kwargs = light.turn_on.call_args
    assert call_kwargs["brightness"] == 100  # U-Tec scale 1-100
    assert ent._optimistic_brightness == 255
    assert ent._pending_brightness_utec == 100
