"""Unit tests for the optimistic-update resolver."""

from optimistic import (
    CONF_OPTIMISTIC_LIGHTS,
    CONF_OPTIMISTIC_LOCKS,
    CONF_OPTIMISTIC_SWITCHES,
    DEFAULT_OPTIMISTIC,
    is_optimistic_enabled,
)


def test_default_constant_is_true():
    assert DEFAULT_OPTIMISTIC is True


def test_missing_key_returns_default_true():
    assert is_optimistic_enabled({}, CONF_OPTIMISTIC_LIGHTS, "dev-1") is True


def test_true_value_returns_true():
    options = {CONF_OPTIMISTIC_LIGHTS: True}
    assert is_optimistic_enabled(options, CONF_OPTIMISTIC_LIGHTS, "dev-1") is True


def test_false_value_returns_false():
    options = {CONF_OPTIMISTIC_LIGHTS: False}
    assert is_optimistic_enabled(options, CONF_OPTIMISTIC_LIGHTS, "dev-1") is False


def test_list_with_match_returns_true():
    options = {CONF_OPTIMISTIC_LIGHTS: ["dev-1", "dev-2"]}
    assert is_optimistic_enabled(options, CONF_OPTIMISTIC_LIGHTS, "dev-1") is True


def test_list_without_match_returns_false():
    options = {CONF_OPTIMISTIC_LIGHTS: ["dev-2"]}
    assert is_optimistic_enabled(options, CONF_OPTIMISTIC_LIGHTS, "dev-1") is False


def test_empty_list_returns_false():
    options = {CONF_OPTIMISTIC_LIGHTS: []}
    assert is_optimistic_enabled(options, CONF_OPTIMISTIC_LIGHTS, "dev-1") is False


def test_different_keys_resolve_independently():
    options = {
        CONF_OPTIMISTIC_LIGHTS: True,
        CONF_OPTIMISTIC_SWITCHES: False,
        CONF_OPTIMISTIC_LOCKS: ["dev-1"],
    }
    assert is_optimistic_enabled(options, CONF_OPTIMISTIC_LIGHTS, "dev-1") is True
    assert is_optimistic_enabled(options, CONF_OPTIMISTIC_SWITCHES, "dev-1") is False
    assert is_optimistic_enabled(options, CONF_OPTIMISTIC_LOCKS, "dev-1") is True
    assert is_optimistic_enabled(options, CONF_OPTIMISTIC_LOCKS, "dev-2") is False
