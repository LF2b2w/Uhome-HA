"""Tests for async_setup_entry end-to-end integration."""

from types import MappingProxyType
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.u_tec import async_setup_entry, async_update_options
from custom_components.u_tec.const import CONF_PUSH_ENABLED, DOMAIN
from tests.common import make_config_entry


@pytest.fixture
def patched_uhomeapi():
    """Replace UHomeApi with a mock for setup-entry tests."""
    with patch("custom_components.u_tec.UHomeApi") as mock_cls:
        instance = MagicMock()
        instance.discover_devices = AsyncMock(return_value={"payload": {"devices": []}})
        instance.get_device_state = AsyncMock(return_value={"payload": {"devices": []}})
        instance.set_push_status = AsyncMock(return_value={})
        mock_cls.return_value = instance
        yield instance


async def test_setup_entry_creates_coordinator_and_stores_in_hass_data(
    hass, patched_uhomeapi,
):
    entry = make_config_entry(options={CONF_PUSH_ENABLED: False})
    entry.add_to_hass(hass)

    with patch(
        "custom_components.u_tec.config_entry_oauth2_flow.async_get_config_entry_implementation"
    ), patch(
        "custom_components.u_tec.config_entry_oauth2_flow.OAuth2Session"
    ) as mock_session, patch(
        "custom_components.u_tec.aiohttp_client.async_get_clientsession",
        return_value=MagicMock(),
    ), patch(
        "custom_components.u_tec.coordinator.UhomeDataUpdateCoordinator.async_config_entry_first_refresh",
        new=AsyncMock(return_value=None),
    ), patch(
        "custom_components.u_tec.coordinator.UhomeDataUpdateCoordinator.async_start_periodic_discovery",
        new=AsyncMock(return_value=None),
    ), patch.object(
        hass.config_entries,
        "async_forward_entry_setups",
        new=AsyncMock(return_value=None),
    ):
        mock_session.return_value = MagicMock()
        result = await async_setup_entry(hass, entry)

    assert result is True
    assert DOMAIN in hass.data
    assert entry.entry_id in hass.data[DOMAIN]
    assert "coordinator" in hass.data[DOMAIN][entry.entry_id]
    assert "api" in hass.data[DOMAIN][entry.entry_id]
    assert "auth_data" in hass.data[DOMAIN][entry.entry_id]
    assert "webhook_handler" in hass.data[DOMAIN][entry.entry_id]


async def test_setup_entry_skips_webhook_when_push_disabled(
    hass, patched_uhomeapi,
):
    entry = make_config_entry(options={CONF_PUSH_ENABLED: False})
    entry.add_to_hass(hass)

    with patch(
        "custom_components.u_tec.config_entry_oauth2_flow.async_get_config_entry_implementation"
    ), patch(
        "custom_components.u_tec.config_entry_oauth2_flow.OAuth2Session"
    ) as mock_session, patch(
        "custom_components.u_tec.aiohttp_client.async_get_clientsession",
        return_value=MagicMock(),
    ), patch(
        "custom_components.u_tec.api.AsyncPushUpdateHandler.async_register_webhook",
        new=AsyncMock(),
    ) as mock_register, patch(
        "custom_components.u_tec.coordinator.UhomeDataUpdateCoordinator.async_config_entry_first_refresh",
        new=AsyncMock(return_value=None),
    ), patch(
        "custom_components.u_tec.coordinator.UhomeDataUpdateCoordinator.async_start_periodic_discovery",
        new=AsyncMock(return_value=None),
    ), patch.object(
        hass.config_entries,
        "async_forward_entry_setups",
        new=AsyncMock(return_value=None),
    ):
        mock_session.return_value = MagicMock()
        await async_setup_entry(hass, entry)

    mock_register.assert_not_awaited()


# --- Push-enabled webhook registration ---


async def test_setup_entry_registers_webhook_when_push_enabled(
    hass, patched_uhomeapi,
):
    entry = make_config_entry(options={CONF_PUSH_ENABLED: True})
    entry.add_to_hass(hass)

    with patch(
        "custom_components.u_tec.config_entry_oauth2_flow.async_get_config_entry_implementation"
    ), patch(
        "custom_components.u_tec.config_entry_oauth2_flow.OAuth2Session"
    ) as mock_session, patch(
        "custom_components.u_tec.aiohttp_client.async_get_clientsession",
        return_value=MagicMock(),
    ), patch(
        "custom_components.u_tec.api.AsyncPushUpdateHandler.async_register_webhook",
        new=AsyncMock(return_value=True),
    ) as mock_register, patch(
        "custom_components.u_tec.coordinator.UhomeDataUpdateCoordinator.async_config_entry_first_refresh",
        new=AsyncMock(return_value=None),
    ), patch(
        "custom_components.u_tec.coordinator.UhomeDataUpdateCoordinator.async_start_periodic_discovery",
        new=AsyncMock(return_value=None),
    ), patch.object(
        hass.config_entries,
        "async_forward_entry_setups",
        new=AsyncMock(return_value=None),
    ):
        mock_session.return_value = MagicMock()
        await async_setup_entry(hass, entry)

    mock_register.assert_awaited_once()


# --- async_update_options push toggle ---


async def test_async_update_options_toggles_webhook_on(hass, patched_uhomeapi):
    entry = make_config_entry(options={CONF_PUSH_ENABLED: False})
    entry.add_to_hass(hass)

    async def _reload_side_effect(_entry_id):
        await async_setup_entry(hass, entry)

    with patch(
        "custom_components.u_tec.config_entry_oauth2_flow.async_get_config_entry_implementation"
    ), patch(
        "custom_components.u_tec.config_entry_oauth2_flow.OAuth2Session"
    ) as mock_session, patch(
        "custom_components.u_tec.aiohttp_client.async_get_clientsession",
        return_value=MagicMock(),
    ), patch(
        "custom_components.u_tec.api.AsyncPushUpdateHandler.async_register_webhook",
        new=AsyncMock(return_value=True),
    ) as mock_register, patch(
        "custom_components.u_tec.coordinator.UhomeDataUpdateCoordinator.async_config_entry_first_refresh",
        new=AsyncMock(return_value=None),
    ), patch(
        "custom_components.u_tec.coordinator.UhomeDataUpdateCoordinator.async_start_periodic_discovery",
        new=AsyncMock(return_value=None),
    ), patch.object(
        hass.config_entries,
        "async_forward_entry_setups",
        new=AsyncMock(return_value=None),
    ), patch.object(
        hass.config_entries,
        "async_reload",
        new=AsyncMock(side_effect=_reload_side_effect),
    ):
        mock_session.return_value = MagicMock()
        await async_setup_entry(hass, entry)

        # Flip push on by directly updating entry options (avoids scheduling the
        # update-listener task, so async_update_options runs only once, explicitly)
        object.__setattr__(entry, "options", MappingProxyType({CONF_PUSH_ENABLED: True}))
        await async_update_options(hass, entry)
        await hass.async_block_till_done()

    mock_register.assert_awaited()  # called at least once via reload path
