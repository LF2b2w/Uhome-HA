"""Tests for OptionsFlowHandler._current_mode helper."""

import pytest

from custom_components.u_tec.config_flow import _current_mode
from tests.common import make_config_entry


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
