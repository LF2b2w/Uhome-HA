"""Tests for OptionsFlowHandler._current_mode helper."""

import pytest
from unittest.mock import MagicMock

from custom_components.u_tec.config_flow import _current_mode
from custom_components.u_tec.const import DOMAIN
from custom_components.u_tec.optimistic import (
    CONF_OPTIMISTIC_LIGHTS,
    CONF_OPTIMISTIC_LOCKS,
    CONF_OPTIMISTIC_SWITCHES,
)
from tests.common import make_config_entry, make_fake_light, make_fake_lock, make_fake_switch


def test_current_mode_returns_all_when_true():
    assert _current_mode(True) == "all"


def test_current_mode_returns_none_when_false():
    assert _current_mode(False) == "none"


def test_current_mode_returns_custom_for_list():
    assert _current_mode(["dev-1", "dev-2"]) == "custom"


def test_current_mode_returns_all_when_none_default():
    # None means option was never set → default is True → "all"
    assert _current_mode(None) == "all"


# --- OptionsFlowHandler menu routing ---


async def test_init_step_shows_menu(hass):
    entry = make_config_entry()
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] == "menu"
    assert "menu_options" in result


async def test_init_step_routes_to_update_push(hass):
    """Selecting 'update_push' should route to the update_push form step."""
    entry = make_config_entry()
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    flow_id = result["flow_id"]

    result = await hass.config_entries.options.async_configure(
        flow_id, user_input={"next_step_id": "update_push"},
    )
    assert result["type"] == "form"
    assert result["step_id"] == "update_push"


# --- Optimistic picker: all-mode ---


async def test_optimistic_all_for_every_type(hass):
    """Setting mode='all' for every type should skip the picker steps and
    produce True for each CONF_OPTIMISTIC_* key."""
    entry = make_config_entry()
    entry.add_to_hass(hass)

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "coordinator": MagicMock(devices={
            "light-1": make_fake_light("light-1"),
            "sw-1": make_fake_switch("sw-1"),
            "lock-1": make_fake_lock("lock-1"),
        }),
    }

    result = await hass.config_entries.options.async_init(entry.entry_id)
    flow_id = result["flow_id"]

    # Navigate to optimistic_updates step
    result = await hass.config_entries.options.async_configure(
        flow_id, user_input={"next_step_id": "optimistic_updates"},
    )
    assert result["type"] == "form"
    assert result["step_id"] == "optimistic_updates"

    # Single combined submission: all three modes = "all"
    result = await hass.config_entries.options.async_configure(
        flow_id, user_input={
            "lights_mode": "all",
            "switches_mode": "all",
            "locks_mode": "all",
        },
    )

    assert result["type"] == "create_entry"
    assert result["data"][CONF_OPTIMISTIC_LIGHTS] is True
    assert result["data"][CONF_OPTIMISTIC_SWITCHES] is True
    assert result["data"][CONF_OPTIMISTIC_LOCKS] is True


# --- Optimistic picker: custom-mode ---


async def test_optimistic_custom_for_lights(hass):
    """Mode='custom' routes to device-selection step; selected devices end up in options list."""
    entry = make_config_entry()
    entry.add_to_hass(hass)

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "coordinator": MagicMock(devices={
            "light-1": make_fake_light("light-1"),
            "light-2": make_fake_light("light-2"),
        }),
    }

    result = await hass.config_entries.options.async_init(entry.entry_id)
    flow_id = result["flow_id"]

    # Enter optimistic_updates step
    result = await hass.config_entries.options.async_configure(
        flow_id, user_input={"next_step_id": "optimistic_updates"},
    )
    assert result["step_id"] == "optimistic_updates"

    # Submit: lights=custom, switches=all, locks=all — should route to pick_lights
    result = await hass.config_entries.options.async_configure(
        flow_id, user_input={
            "lights_mode": "custom",
            "switches_mode": "all",
            "locks_mode": "all",
        },
    )
    assert result["type"] == "form"
    assert result["step_id"] == "pick_lights"

    # Pick light-1 — form field key is the CONF_OPTIMISTIC_LIGHTS constant
    result = await hass.config_entries.options.async_configure(
        flow_id, user_input={CONF_OPTIMISTIC_LIGHTS: ["light-1"]},
    )
    assert result["type"] == "create_entry"
    assert result["data"][CONF_OPTIMISTIC_LIGHTS] == ["light-1"]
    assert result["data"][CONF_OPTIMISTIC_SWITCHES] is True
    assert result["data"][CONF_OPTIMISTIC_LOCKS] is True


# --- Optimistic picker: none-mode ---


async def test_optimistic_none_skips_picker(hass):
    """Mode='none' for a type stores False and does NOT route to its picker step."""
    entry = make_config_entry()
    entry.add_to_hass(hass)

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "coordinator": MagicMock(devices={
            "light-1": make_fake_light("light-1"),
        }),
    }

    result = await hass.config_entries.options.async_init(entry.entry_id)
    flow_id = result["flow_id"]
    result = await hass.config_entries.options.async_configure(
        flow_id, user_input={"next_step_id": "optimistic_updates"},
    )

    # Lights=none, switches=all, locks=all — no picker fires, goes straight to create_entry
    result = await hass.config_entries.options.async_configure(
        flow_id, user_input={
            "lights_mode": "none",
            "switches_mode": "all",
            "locks_mode": "all",
        },
    )
    assert result["type"] == "create_entry"
    assert result["data"][CONF_OPTIMISTIC_LIGHTS] is False
    assert result["data"][CONF_OPTIMISTIC_SWITCHES] is True
    assert result["data"][CONF_OPTIMISTIC_LOCKS] is True
