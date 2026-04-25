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


# --- _async_update_data ---

from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import UpdateFailed
from utec_py.exceptions import ApiError, AuthenticationError


async def test_async_update_data_empty_when_no_devices(coordinator):
    result = await coordinator._async_update_data()
    assert result == {}
    coordinator.api.get_device_state.assert_not_called()


async def test_async_update_data_bulk_fetches_all_devices(coordinator, mock_uhome_api):
    sw1 = make_fake_switch("sw-1")
    sw2 = make_fake_switch("sw-2")
    sw1.get_state_data = lambda: {"st.switch": {"switch": "on"}}
    sw2.get_state_data = lambda: {"st.switch": {"switch": "off"}}
    coordinator.devices["sw-1"] = sw1
    coordinator.devices["sw-2"] = sw2
    mock_uhome_api.get_device_state.return_value = {
        "payload": {"devices": [
            {"id": "sw-1", "states": [{"capability": "st.switch", "name": "switch", "value": "on"}]},
            {"id": "sw-2", "states": [{"capability": "st.switch", "name": "switch", "value": "off"}]},
        ]}
    }

    result = await coordinator._async_update_data()

    assert set(result.keys()) == {"sw-1", "sw-2"}
    mock_uhome_api.get_device_state.assert_awaited_once_with(["sw-1", "sw-2"], None)


async def test_async_update_data_auth_error_raises_config_entry_auth_failed(
    coordinator, mock_uhome_api,
):
    coordinator.devices["sw-1"] = make_fake_switch("sw-1")
    mock_uhome_api.get_device_state.side_effect = AuthenticationError("bad token")

    with pytest.raises(ConfigEntryAuthFailed, match="Credentials expired"):
        await coordinator._async_update_data()


async def test_async_update_data_api_error_raises_update_failed(
    coordinator, mock_uhome_api,
):
    coordinator.devices["sw-1"] = make_fake_switch("sw-1")
    mock_uhome_api.get_device_state.side_effect = ApiError(500, "oops")

    with pytest.raises(UpdateFailed, match="Error communicating"):
        await coordinator._async_update_data()
