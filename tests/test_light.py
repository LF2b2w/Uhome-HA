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


# --- _handle_coordinator_update state-clear ---


def test_coordinator_update_clears_optimistic_when_device_confirms(coord_with_light):
    coord, light = coord_with_light
    ent = UhomeLightEntity(coord, "light-1")
    ent._optimistic_is_on = True
    ent.async_write_ha_state = MagicMock()
    light.is_on = True  # device now reports the same

    ent._handle_coordinator_update()

    assert ent._optimistic_is_on is None


def test_coordinator_update_keeps_optimistic_when_device_disagrees(coord_with_light):
    coord, light = coord_with_light
    ent = UhomeLightEntity(coord, "light-1")
    ent._optimistic_is_on = True
    ent.async_write_ha_state = MagicMock()
    light.is_on = False  # device still reports old state

    ent._handle_coordinator_update()

    assert ent._optimistic_is_on is True


def test_brightness_pending_clears_only_on_exact_match(coord_with_light):
    coord, light = coord_with_light
    ent = UhomeLightEntity(coord, "light-1")
    ent._optimistic_brightness = 200
    ent._pending_brightness_utec = 80
    ent.async_write_ha_state = MagicMock()
    light.brightness = 80  # device caught up

    ent._handle_coordinator_update()

    assert ent._optimistic_brightness is None
    assert ent._pending_brightness_utec is None


def test_brightness_pending_persists_when_device_differs(coord_with_light):
    coord, light = coord_with_light
    ent = UhomeLightEntity(coord, "light-1")
    ent._optimistic_brightness = 200
    ent._pending_brightness_utec = 80
    ent.async_write_ha_state = MagicMock()
    light.brightness = 50  # device hasn't caught up

    ent._handle_coordinator_update()

    assert ent._optimistic_brightness == 200
    assert ent._pending_brightness_utec == 80


# --- assumed_state + error handling ---


def test_assumed_state_true_when_optimistic_and_pending(coord_with_light):
    coord, light = coord_with_light
    ent = UhomeLightEntity(coord, "light-1")
    ent._optimistic_is_on = True
    assert ent.assumed_state is True


def test_assumed_state_false_when_optimistic_disabled(hass):
    entry = make_config_entry(options={CONF_OPTIMISTIC_LIGHTS: False})
    entry.add_to_hass(hass)
    light = make_fake_light("light-1")
    coord = MagicMock()
    coord.devices = {"light-1": light}
    coord.config_entry = entry
    coord.last_update_success = True
    coord.data = {}

    ent = UhomeLightEntity(coord, "light-1")
    ent._optimistic_is_on = True  # would be set, but optimistic disabled
    assert ent.assumed_state is False


async def test_turn_on_wraps_device_error(coord_with_light, hass):
    from homeassistant.exceptions import HomeAssistantError
    from utec_py.exceptions import DeviceError

    coord, light = coord_with_light
    light.turn_on.side_effect = DeviceError("nope")
    ent = UhomeLightEntity(coord, "light-1")
    ent.hass = hass
    ent.entity_id = "light.fake_light"

    with pytest.raises(HomeAssistantError):
        await ent.async_turn_on()


async def test_turn_off_wraps_device_error(coord_with_light, hass):
    from homeassistant.exceptions import HomeAssistantError
    from utec_py.exceptions import DeviceError

    coord, light = coord_with_light
    light.turn_off.side_effect = DeviceError("nope")
    ent = UhomeLightEntity(coord, "light-1")
    ent.hass = hass
    ent.entity_id = "light.fake_light"

    with pytest.raises(HomeAssistantError):
        await ent.async_turn_off()


# ============================================================
# Task 24c — coverage gap fill
# ============================================================

# --- lines 45-49: async_setup_entry isinstance filter ---


async def test_setup_entry_filters_non_light_devices(hass):
    """Coordinator with mixed devices; only UhomeLight instances become entities."""
    from custom_components.u_tec.light import async_setup_entry
    from tests.common import make_fake_switch

    entry = make_config_entry()
    entry.add_to_hass(hass)

    light = make_fake_light("light-1")
    switch = make_fake_switch("sw-1")

    coord = MagicMock()
    coord.devices = {"light-1": light, "sw-1": switch}
    coord.config_entry = entry
    coord.last_update_success = True
    coord.data = {}

    hass.data.setdefault("u_tec", {})
    hass.data["u_tec"][entry.entry_id] = {"coordinator": coord}

    added = []

    def fake_add(entities, **kwargs):
        added.extend(list(entities))

    await async_setup_entry(hass, entry, fake_add)

    assert len(added) == 1
    assert added[0]._device.device_id == "light-1"


# --- lines 100->102, 103: is_on optimistic branch ---


def test_is_on_returns_optimistic_when_set(coord_with_light):
    """Line 100->102: _optimistic_is_on set → returns optimistic value."""
    coord, light = coord_with_light
    light.is_on = False
    ent = UhomeLightEntity(coord, "light-1")
    ent._optimistic_is_on = True
    assert ent.is_on is True


def test_is_on_delegates_to_device_when_no_optimistic(coord_with_light):
    """Line 103: _optimistic_is_on is None → delegate to device."""
    coord, light = coord_with_light
    light.is_on = True
    ent = UhomeLightEntity(coord, "light-1")
    ent._optimistic_is_on = None
    assert ent.is_on is True


# --- line 105: brightness optimistic branch ---


def test_brightness_returns_optimistic_when_set(coord_with_light):
    """Line 105: _optimistic_brightness set → return it directly."""
    coord, light = coord_with_light
    ent = UhomeLightEntity(coord, "light-1")
    ent._optimistic_brightness = 128
    assert ent.brightness == 128


# --- line 109: brightness returns None when device brightness is None ---


def test_brightness_returns_none_when_device_brightness_none(coord_with_light):
    """Line 109: device.brightness=None → brightness returns None."""
    coord, light = coord_with_light
    light.brightness = None
    ent = UhomeLightEntity(coord, "light-1")
    assert ent.brightness is None


# --- line 113: brightness converts via value_to_brightness ---


def test_brightness_converts_device_brightness(coord_with_light):
    """Line 113: device.brightness=50 → value_to_brightness((1,100), 50)."""
    from homeassistant.util.color import value_to_brightness

    coord, light = coord_with_light
    light.brightness = 50
    ent = UhomeLightEntity(coord, "light-1")
    expected = value_to_brightness((1, 100), 50)
    assert ent.brightness == expected


# --- line 115: assumed_state True when optimistic mode on and _optimistic_is_on set ---


def test_assumed_state_true_when_only_optimistic_is_on(coord_with_light):
    """Line 115: optimistic mode on + _optimistic_is_on set → assumed_state True."""
    coord, light = coord_with_light
    ent = UhomeLightEntity(coord, "light-1")
    ent._optimistic_is_on = True
    ent._optimistic_brightness = None
    assert ent.assumed_state is True


# --- line 119: assumed_state True when only _optimistic_brightness is set ---


def test_assumed_state_true_when_only_optimistic_brightness(coord_with_light):
    """Line 119: optimistic mode on + _optimistic_brightness set → assumed_state True."""
    coord, light = coord_with_light
    ent = UhomeLightEntity(coord, "light-1")
    ent._optimistic_is_on = None
    ent._optimistic_brightness = 200
    assert ent.assumed_state is True


# --- line 132: coordinator update clears _optimistic_is_on once device matches ---


def test_coordinator_update_clears_optimistic_is_on_on_match(coord_with_light):
    """Line 132: device.is_on matches _optimistic_is_on → clear optimistic."""
    coord, light = coord_with_light
    ent = UhomeLightEntity(coord, "light-1")
    ent._optimistic_is_on = False
    ent.async_write_ha_state = MagicMock()
    light.is_on = False  # device now confirms off

    ent._handle_coordinator_update()

    assert ent._optimistic_is_on is None


# --- line 138: coordinator clears brightness when pending matches device ---


def test_coordinator_update_clears_brightness_on_exact_match(coord_with_light):
    """Line 138: pending matches device brightness → clear both pending + optimistic."""
    coord, light = coord_with_light
    ent = UhomeLightEntity(coord, "light-1")
    ent._optimistic_brightness = 180
    ent._pending_brightness_utec = 70
    ent.async_write_ha_state = MagicMock()
    light.brightness = 70  # device confirmed the 70 we sent

    ent._handle_coordinator_update()

    assert ent._optimistic_brightness is None
    assert ent._pending_brightness_utec is None


# --- lines 144-148: no pending → clear optimistic_brightness via else branch ---


def test_coordinator_update_clears_optimistic_brightness_when_no_pending(coord_with_light):
    """Lines 144-148: _pending_brightness_utec=None → else clears _optimistic_brightness."""
    coord, light = coord_with_light
    ent = UhomeLightEntity(coord, "light-1")
    ent._optimistic_brightness = 100
    ent._pending_brightness_utec = None
    ent.async_write_ha_state = MagicMock()

    ent._handle_coordinator_update()

    assert ent._optimistic_brightness is None


# --- line 185: rgb_color delegates to device ---


def test_rgb_color_returns_device_value(coord_with_light):
    """Line 185: rgb_color returns device.rgb_color."""
    coord, light = coord_with_light
    light.rgb_color = (255, 128, 0)
    ent = UhomeLightEntity(coord, "light-1")
    assert ent.rgb_color == (255, 128, 0)


# --- line 192: color_temp_kelvin delegates to device ---


def test_color_temp_kelvin_returns_device_value(coord_with_light):
    """Line 192: color_temp_kelvin returns device.color_temp."""
    coord, light = coord_with_light
    light.color_temp = 4000
    ent = UhomeLightEntity(coord, "light-1")
    assert ent.color_temp_kelvin == 4000


# --- line 206, 209: turn_on DeviceError path (log + raise) ---


async def test_turn_on_device_error_logs_and_raises(coord_with_light, hass):
    """Lines 206, 209: DeviceError → log error + raise HomeAssistantError."""
    from homeassistant.exceptions import HomeAssistantError
    from utec_py.exceptions import DeviceError

    coord, light = coord_with_light
    light.turn_on.side_effect = DeviceError("boom")
    ent = UhomeLightEntity(coord, "light-1")
    ent.hass = hass
    ent.entity_id = "light.fake_light"
    ent.async_write_ha_state = MagicMock()

    with pytest.raises(HomeAssistantError, match="Failed to turn on light"):
        await ent.async_turn_on()

    # Optimistic state must NOT have been set (error happened before that block)
    assert ent._optimistic_is_on is None


# --- line 213->exit: turn_on with optimistic disabled skips optimistic writes ---


async def test_turn_on_no_optimistic_write_when_disabled(hass):
    """Line 213->exit: optimistic off → no _optimistic_is_on set, no async_write_ha_state."""
    entry = make_config_entry(options={CONF_OPTIMISTIC_LIGHTS: False})
    entry.add_to_hass(hass)
    light = make_fake_light("light-1")
    coord = MagicMock()
    coord.devices = {"light-1": light}
    coord.config_entry = entry
    coord.last_update_success = True
    coord.data = {}

    ent = UhomeLightEntity(coord, "light-1")
    ent.hass = hass
    ent.entity_id = "light.fake_light"
    ent.async_write_ha_state = MagicMock()

    await ent.async_turn_on()

    assert ent._optimistic_is_on is None
    ent.async_write_ha_state.assert_not_called()


# --- line 229->exit: turn_off DeviceError path ---


async def test_turn_off_device_error_logs_and_raises(coord_with_light, hass):
    """Line 229->exit: DeviceError in turn_off → raise HomeAssistantError."""
    from homeassistant.exceptions import HomeAssistantError
    from utec_py.exceptions import DeviceError

    coord, light = coord_with_light
    light.turn_off.side_effect = DeviceError("bang")
    ent = UhomeLightEntity(coord, "light-1")
    ent.hass = hass
    ent.entity_id = "light.fake_light"
    ent.async_write_ha_state = MagicMock()

    with pytest.raises(HomeAssistantError, match="Failed to turn off light"):
        await ent.async_turn_off()


# --- lines 240-242: async_added_to_hass connects dispatcher ---


async def test_async_added_to_hass_connects_dispatcher(coord_with_light, hass):
    """Lines 240-242: async_added_to_hass registers dispatcher for push updates."""
    from unittest.mock import patch

    coord, light = coord_with_light
    ent = UhomeLightEntity(coord, "light-1")
    ent.hass = hass
    ent.entity_id = "light.fake_light"
    ent.async_write_ha_state = MagicMock()

    with patch(
        "custom_components.u_tec.light.async_dispatcher_connect",
        return_value=lambda: None,
    ) as mock_connect:
        # async_added_to_hass calls super() which needs the coordinator wired up
        ent.async_on_remove = MagicMock()
        await ent.async_added_to_hass()

    mock_connect.assert_called_once()
    call_args = mock_connect.call_args
    signal = call_args[0][1]
    assert signal == f"u_tec_device_update_{light.device_id}"


# --- line 253: _handle_push_update calls async_write_ha_state ---


def test_handle_push_update_calls_write_ha_state(coord_with_light):
    """Line 253: _handle_push_update → async_write_ha_state called."""
    coord, light = coord_with_light
    ent = UhomeLightEntity(coord, "light-1")
    ent.async_write_ha_state = MagicMock()

    ent._handle_push_update({"some": "data"})

    ent.async_write_ha_state.assert_called_once()
