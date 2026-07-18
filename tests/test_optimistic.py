"""Unit tests for the optimistic-update resolver."""

import pytest

from custom_components.u_tec.optimistic import (
    CONF_OPTIMISTIC_LIGHTS,
    CONF_OPTIMISTIC_LOCKS,
    CONF_OPTIMISTIC_SWITCHES,
    DEFAULT_OPTIMISTIC,
    is_optimistic_enabled,
    push_asserts_state,
)


@pytest.mark.parametrize(
    "push_data,expected",
    [
        ({"st.lock": {"lockState": "Locked"}}, True),  # capability + attr present
        ({"st.lock": {"lockState": "Unlocked"}}, True),  # value doesn't matter
        ({"st.doorSensor": {"doorState": "open"}}, False),  # different capability
        ({"st.lock": {"battery": 3}}, False),  # capability present, wrong attr
        ({"st.lock": {}}, False),  # capability present, no attrs
        ({}, False),  # empty
        (None, False),  # not a dict
        ("garbage", False),  # not a dict
        ({"st.lock": "notadict"}, False),  # capability value isn't a dict
    ],
)
def test_push_asserts_state(push_data, expected):
    assert push_asserts_state(push_data, "st.lock", "lockState") is expected


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
