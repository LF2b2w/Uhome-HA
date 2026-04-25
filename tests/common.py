"""Shared test helpers for u_tec integration tests."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.u_tec.const import DOMAIN


def make_config_entry(
    *,
    entry_id: str = "test-entry-id",
    data: dict | None = None,
    options: dict | None = None,
    version: int = 2,
) -> MockConfigEntry:
    """Build a MockConfigEntry for the u_tec integration."""
    return MockConfigEntry(
        domain=DOMAIN,
        entry_id=entry_id,
        data=data or {
            "auth_implementation": "u_tec",
            "token": {
                "access_token": "test-access",
                "refresh_token": "test-refresh",
                "expires_at": 9999999999,
            },
        },
        options=options or {},
        version=version,
        minor_version=1,
        unique_id=entry_id,
    )


def make_fake_light(
    device_id: str = "light-1",
    name: str = "Fake Light",
    *,
    is_on: bool = False,
    brightness: int | None = None,
    rgb_color: tuple | None = None,
    color_temp: int | None = None,
    available: bool = True,
    supported_capabilities: set | None = None,
) -> MagicMock:
    """Return a MagicMock spec-bound to utec_py.devices.light.Light."""
    from utec_py.devices.light import Light

    mock = MagicMock(spec=Light)
    mock.device_id = device_id
    mock.name = name
    mock.manufacturer = "U-Tec"
    mock.model = "TestLight"
    mock.hw_version = "1.0"
    mock.available = available
    mock.is_on = is_on
    mock.brightness = brightness
    mock.rgb_color = rgb_color
    mock.color_temp = color_temp
    mock.supported_capabilities = supported_capabilities or {
        "st.switch",
        "st.brightness",
        "st.switchLevel",
    }
    mock.turn_on = AsyncMock(return_value=None)
    mock.turn_off = AsyncMock(return_value=None)
    mock.update = AsyncMock(return_value=None)
    mock.update_state_data = AsyncMock(return_value=None)
    return mock


def make_fake_switch(
    device_id: str = "sw-1",
    name: str = "Fake Switch",
    *,
    is_on: bool = False,
    available: bool = True,
) -> MagicMock:
    """Return a MagicMock spec-bound to utec_py.devices.switch.Switch."""
    from utec_py.devices.switch import Switch

    mock = MagicMock(spec=Switch)
    mock.device_id = device_id
    mock.name = name
    mock.manufacturer = "U-Tec"
    mock.model = "TestSwitch"
    mock.hw_version = "1.0"
    mock.available = available
    mock.is_on = is_on
    mock.supported_capabilities = {"st.switch"}
    mock.turn_on = AsyncMock(return_value=None)
    mock.turn_off = AsyncMock(return_value=None)
    mock.update = AsyncMock(return_value=None)
    mock.update_state_data = AsyncMock(return_value=None)
    return mock


def make_fake_lock(
    device_id: str = "lock-1",
    name: str = "Fake Lock",
    *,
    is_locked: bool = True,
    is_jammed: bool = False,
    available: bool = True,
    has_door_sensor: bool = False,
    is_door_open: bool = False,
    battery_level: int = 90,
    lock_mode: str = "normal",
) -> MagicMock:
    """Return a MagicMock spec-bound to utec_py.devices.lock.Lock."""
    from utec_py.devices.lock import Lock

    mock = MagicMock(spec=Lock)
    mock.device_id = device_id
    mock.name = name
    mock.manufacturer = "U-Tec"
    mock.model = "TestLock"
    mock.hw_version = "1.0"
    mock.available = available
    mock.is_locked = is_locked
    mock.is_jammed = is_jammed
    mock.has_door_sensor = has_door_sensor
    mock.is_door_open = is_door_open
    mock.battery_level = battery_level
    mock.battery_status = "normal"
    mock.lock_mode = lock_mode
    mock.supported_capabilities = {"st.lock"}
    mock.lock = AsyncMock(return_value=None)
    mock.unlock = AsyncMock(return_value=None)
    mock.update = AsyncMock(return_value=None)
    mock.update_state_data = AsyncMock(return_value=None)
    return mock
