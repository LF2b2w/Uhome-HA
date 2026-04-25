"""Tests for custom_components.u_tec.diagnostics."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.u_tec.diagnostics import async_get_config_entry_diagnostics
from tests.common import make_config_entry, make_fake_lock


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_hass_data(hass, entry, coord, api):
    """Wire entry + coord + api into hass.data the same way __init__ does."""
    from custom_components.u_tec.const import DOMAIN

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "coordinator": coord,
        "api": api,
    }


def _make_coord(devices=None, last_update_success=True):
    coord = MagicMock()
    coord.devices = devices if devices is not None else {}
    coord.last_update_success = last_update_success
    return coord


# ---------------------------------------------------------------------------
# 1. Token redaction
# ---------------------------------------------------------------------------

async def test_diagnostics_redacts_tokens(hass, mock_uhome_api):
    """Sensitive token strings must not appear anywhere in the result."""
    entry = make_config_entry(
        data={
            "token": {
                "access_token": "SECRET-ACCESS",
                "refresh_token": "SECRET-REFRESH",
            },
            "auth_implementation": "u_tec",
        }
    )
    entry.add_to_hass(hass)

    coord = _make_coord()
    _make_hass_data(hass, entry, coord, mock_uhome_api)

    result = await async_get_config_entry_diagnostics(hass, entry)
    s = str(result)
    assert "SECRET-ACCESS" not in s
    assert "SECRET-REFRESH" not in s


# ---------------------------------------------------------------------------
# 2-4. discover_devices error branches
# ---------------------------------------------------------------------------

async def test_diagnostics_handles_discover_connection_error(hass, mock_uhome_api):
    """ConnectionError from discover_devices produces a structured error entry."""
    entry = make_config_entry()
    entry.add_to_hass(hass)

    mock_uhome_api.discover_devices = AsyncMock(
        side_effect=ConnectionError("net")
    )
    coord = _make_coord()
    _make_hass_data(hass, entry, coord, mock_uhome_api)

    result = await async_get_config_entry_diagnostics(hass, entry)
    assert result["discovery_data"]["error"].startswith("Connection error:")


async def test_diagnostics_handles_discover_timeout_error(hass, mock_uhome_api):
    """TimeoutError from discover_devices produces a structured error entry."""
    entry = make_config_entry()
    entry.add_to_hass(hass)

    mock_uhome_api.discover_devices = AsyncMock(
        side_effect=TimeoutError("timed out")
    )
    coord = _make_coord()
    _make_hass_data(hass, entry, coord, mock_uhome_api)

    result = await async_get_config_entry_diagnostics(hass, entry)
    assert result["discovery_data"]["error"].startswith("Timeout error:")


async def test_diagnostics_handles_discover_value_error(hass, mock_uhome_api):
    """ValueError from discover_devices produces a structured error entry."""
    entry = make_config_entry()
    entry.add_to_hass(hass)

    mock_uhome_api.discover_devices = AsyncMock(
        side_effect=ValueError("bad value")
    )
    coord = _make_coord()
    _make_hass_data(hass, entry, coord, mock_uhome_api)

    result = await async_get_config_entry_diagnostics(hass, entry)
    assert result["discovery_data"]["error"].startswith("Value error:")


# ---------------------------------------------------------------------------
# 5. Happy-path: device property serialisation + query loop
# ---------------------------------------------------------------------------

async def test_diagnostics_serialises_device_properties_and_query(
    hass, mock_uhome_api
):
    """With one device in the coordinator, diagnostics reflects its properties."""
    entry = make_config_entry()
    entry.add_to_hass(hass)

    device_id = "lock-1"
    fake_lock = make_fake_lock(device_id=device_id, name="Fake Lock")
    # diagnostics.py accesses handle_type, category, get_state_data directly
    fake_lock.handle_type = "utec-lock"
    fake_lock.category = MagicMock(value="lock")
    fake_lock.get_state_data = MagicMock(return_value={"foo": "bar"})

    coord = _make_coord(devices={device_id: fake_lock}, last_update_success=True)
    # Use a key that is NOT in REDACT_KEYS so the assertion is stable after redaction
    query_return = {"payload": {"devices": [{"status": "ok"}]}}
    mock_uhome_api.query_device = AsyncMock(return_value=query_return)

    _make_hass_data(hass, entry, coord, mock_uhome_api)

    result = await async_get_config_entry_diagnostics(hass, entry)

    # Top-level keys
    assert set(result.keys()) == {
        "config_entry",
        "coordinator_data",
        "devices",
        "discovery_data",
        "query_data",
    }

    # Device data
    assert device_id in result["devices"]
    assert result["devices"][device_id]["name"] == "Fake Lock"

    # Query data – value matches what the API returned (no REDACT_KEYS present)
    assert device_id in result["query_data"]
    assert result["query_data"][device_id] == query_return

    # Coordinator fields
    assert result["coordinator_data"]["last_update_success"] is True
    assert result["coordinator_data"]["device_count"] == 1


# ---------------------------------------------------------------------------
# 6. query_device error branch (ValueError)
# ---------------------------------------------------------------------------

async def test_diagnostics_handles_query_value_error(hass, mock_uhome_api):
    """ValueError from query_device is captured per-device in query_data."""
    entry = make_config_entry()
    entry.add_to_hass(hass)

    device_id = "lock-1"
    fake_lock = make_fake_lock(device_id=device_id)
    fake_lock.handle_type = "utec-lock"
    fake_lock.category = MagicMock(value="lock")
    fake_lock.get_state_data = MagicMock(return_value={})

    coord = _make_coord(devices={device_id: fake_lock})
    mock_uhome_api.query_device = AsyncMock(side_effect=ValueError("bad"))
    _make_hass_data(hass, entry, coord, mock_uhome_api)

    result = await async_get_config_entry_diagnostics(hass, entry)
    assert result["query_data"][device_id]["error"] == "bad"


# ---------------------------------------------------------------------------
# 7. query_device ConnectionError + TimeoutError branches
# ---------------------------------------------------------------------------

async def test_diagnostics_handles_query_connection_error(hass, mock_uhome_api):
    """ConnectionError from query_device is captured per-device in query_data."""
    entry = make_config_entry()
    entry.add_to_hass(hass)

    device_id = "lock-1"
    fake_lock = make_fake_lock(device_id=device_id)
    fake_lock.handle_type = "utec-lock"
    fake_lock.category = MagicMock(value="lock")
    fake_lock.get_state_data = MagicMock(return_value={})

    coord = _make_coord(devices={device_id: fake_lock})
    mock_uhome_api.query_device = AsyncMock(side_effect=ConnectionError("net"))
    _make_hass_data(hass, entry, coord, mock_uhome_api)

    result = await async_get_config_entry_diagnostics(hass, entry)
    assert result["query_data"][device_id]["error"].startswith("Connection error:")


async def test_diagnostics_handles_query_timeout_error(hass, mock_uhome_api):
    """TimeoutError from query_device is captured per-device in query_data."""
    entry = make_config_entry()
    entry.add_to_hass(hass)

    device_id = "lock-1"
    fake_lock = make_fake_lock(device_id=device_id)
    fake_lock.handle_type = "utec-lock"
    fake_lock.category = MagicMock(value="lock")
    fake_lock.get_state_data = MagicMock(return_value={})

    coord = _make_coord(devices={device_id: fake_lock})
    mock_uhome_api.query_device = AsyncMock(side_effect=TimeoutError("timed out"))
    _make_hass_data(hass, entry, coord, mock_uhome_api)

    result = await async_get_config_entry_diagnostics(hass, entry)
    assert result["query_data"][device_id]["error"].startswith("Timeout error:")


# ---------------------------------------------------------------------------
# 8. Property reflection: non-serializable (TypeError), AttributeError,
#    ValueError during property access
# ---------------------------------------------------------------------------

async def test_diagnostics_handles_non_serializable_property(hass, mock_uhome_api):
    """A property whose value can't be JSON-serialised falls back to str()."""
    entry = make_config_entry()
    entry.add_to_hass(hass)

    device_id = "lock-1"
    fake_lock = make_fake_lock(device_id=device_id)
    fake_lock.handle_type = "utec-lock"
    fake_lock.category = MagicMock(value="lock")
    fake_lock.get_state_data = MagicMock(return_value={})

    # Expose a non-serialisable attribute directly on the MagicMock so dir()
    # sees it.  We use a plain object with no __str__ override — json.dumps
    # will raise TypeError and the code falls back to str(value).
    class _Unserializable:
        def __repr__(self):
            return "unserializable-object"

    # Patch the MagicMock so the property appears as a non-callable attribute
    # that dir() can find.  We attach it directly to the instance's __dict__
    # so MagicMock's spec doesn't block it.
    fake_lock.__dict__["weird_prop"] = _Unserializable()

    coord = _make_coord(devices={device_id: fake_lock})
    _make_hass_data(hass, entry, coord, mock_uhome_api)

    result = await async_get_config_entry_diagnostics(hass, entry)
    # Just confirm it ran without exception and the device entry is present
    assert device_id in result["devices"]
