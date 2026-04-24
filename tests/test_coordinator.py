"""Tests for UhomeDataUpdateCoordinator."""

from unittest.mock import AsyncMock

import pytest

from custom_components.u_tec.coordinator import UhomeDataUpdateCoordinator
from tests.common import make_config_entry, make_fake_switch


@pytest.fixture
async def coordinator(hass, mock_uhome_api):
    entry = make_config_entry()
    entry.add_to_hass(hass)
    coord = UhomeDataUpdateCoordinator(
        hass, mock_uhome_api, config_entry=entry, scan_interval=10, discovery_interval=300,
    )
    return coord


async def test_update_push_data_flat_list_shape_routes_to_device(coordinator):
    """Issue #30 regression: payload can be a flat list, not a dict."""
    sw = make_fake_switch("sw-1")
    coordinator.devices["sw-1"] = sw
    push_data = [
        {"id": "sw-1", "states": [
            {"capability": "st.switch", "name": "switch", "value": "on"},
        ]},
    ]

    await coordinator.update_push_data(push_data)

    sw.update_state_data.assert_awaited_once_with(push_data[0])


async def test_update_push_data_nested_dict_shape(coordinator):
    sw = make_fake_switch("sw-1")
    coordinator.devices["sw-1"] = sw
    push_data = {"payload": {"devices": [
        {"id": "sw-1", "states": [
            {"capability": "st.switch", "name": "switch", "value": "on"},
        ]},
    ]}}

    await coordinator.update_push_data(push_data)

    sw.update_state_data.assert_awaited_once()


async def test_update_push_data_payload_is_list_shape(coordinator):
    """Edge case: `payload` key points to a list, not a dict."""
    sw = make_fake_switch("sw-1")
    coordinator.devices["sw-1"] = sw
    push_data = {"payload": [
        {"id": "sw-1", "states": [{"capability": "st.switch", "name": "switch", "value": "on"}]},
    ]}

    await coordinator.update_push_data(push_data)

    sw.update_state_data.assert_awaited_once()


async def test_update_push_data_missing_device_id_is_skipped(coordinator):
    sw = make_fake_switch("sw-1")
    coordinator.devices["sw-1"] = sw
    push_data = [{"states": [{"capability": "x", "name": "y", "value": 1}]}]

    await coordinator.update_push_data(push_data)

    sw.update_state_data.assert_not_awaited()


async def test_update_push_data_unknown_device_id_is_skipped(coordinator):
    sw = make_fake_switch("sw-1")
    coordinator.devices["sw-1"] = sw
    push_data = [{"id": "unknown-999", "states": []}]

    await coordinator.update_push_data(push_data)

    sw.update_state_data.assert_not_awaited()


async def test_update_push_data_non_dict_entry_is_skipped(coordinator):
    sw = make_fake_switch("sw-1")
    coordinator.devices["sw-1"] = sw
    push_data = [["not", "a", "dict"], {"id": "sw-1", "states": []}]

    await coordinator.update_push_data(push_data)

    # The valid second entry still routes
    sw.update_state_data.assert_awaited_once()


async def test_update_push_data_respects_push_device_allowlist(coordinator):
    sw = make_fake_switch("sw-1")
    other = make_fake_switch("sw-2")
    coordinator.devices["sw-1"] = sw
    coordinator.devices["sw-2"] = other
    coordinator.push_devices = ["sw-1"]  # only sw-1 allowed

    push_data = [
        {"id": "sw-1", "states": []},
        {"id": "sw-2", "states": []},
    ]
    await coordinator.update_push_data(push_data)

    sw.update_state_data.assert_awaited_once()
    other.update_state_data.assert_not_awaited()


async def test_update_push_data_unrecognised_top_level_type_is_noop(coordinator):
    sw = make_fake_switch("sw-1")
    coordinator.devices["sw-1"] = sw

    await coordinator.update_push_data("garbage-string")
    await coordinator.update_push_data(None)
    await coordinator.update_push_data(42)

    sw.update_state_data.assert_not_awaited()
