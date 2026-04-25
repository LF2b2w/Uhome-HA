"""Tests for OptionsFlowHandler._current_mode helper."""

import pytest

from custom_components.u_tec.config_flow import _current_mode


def test_current_mode_returns_all_when_true():
    assert _current_mode(True) == "all"


def test_current_mode_returns_none_when_false():
    assert _current_mode(False) == "none"


def test_current_mode_returns_custom_for_list():
    assert _current_mode(["dev-1", "dev-2"]) == "custom"


def test_current_mode_returns_all_when_none_default():
    # None means option was never set → default is True → "all"
    assert _current_mode(None) == "all"
