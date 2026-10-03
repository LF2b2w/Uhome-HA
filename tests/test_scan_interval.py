"""Tests for scan_interval resolution and clamping."""

from custom_components.u_tec import _resolve_scan_interval
from custom_components.u_tec.const import (
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
    YAML_CONFIG_KEY,
)
from tests.common import make_config_entry


def test_resolve_prefers_ui_option(hass):
    entry = make_config_entry(options={CONF_SCAN_INTERVAL: 120})
    hass.data.setdefault(DOMAIN, {})[YAML_CONFIG_KEY] = {CONF_SCAN_INTERVAL: 30}
    assert _resolve_scan_interval(hass, entry) == 120


def test_resolve_falls_back_to_yaml(hass):
    entry = make_config_entry(options={})
    hass.data.setdefault(DOMAIN, {})[YAML_CONFIG_KEY] = {CONF_SCAN_INTERVAL: 45}
    assert _resolve_scan_interval(hass, entry) == 45


def test_resolve_falls_back_to_default(hass):
    entry = make_config_entry(options={})
    hass.data.setdefault(DOMAIN, {})
    assert _resolve_scan_interval(hass, entry) == DEFAULT_SCAN_INTERVAL


def test_resolve_clamps_yaml_below_minimum(hass):
    entry = make_config_entry(options={})
    hass.data.setdefault(DOMAIN, {})[YAML_CONFIG_KEY] = {CONF_SCAN_INTERVAL: 5}
    assert _resolve_scan_interval(hass, entry) == MIN_SCAN_INTERVAL


def test_resolve_clamps_above_maximum(hass):
    entry = make_config_entry(options={CONF_SCAN_INTERVAL: 99999})
    assert _resolve_scan_interval(hass, entry) == MAX_SCAN_INTERVAL
