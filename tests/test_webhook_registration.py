"""Tests for AsyncPushUpdateHandler.async_register_webhook — URL resolution."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.helpers.network import NoURLAvailableError

from custom_components.u_tec.api import AsyncPushUpdateHandler


async def test_register_succeeds_with_external_url(hass, mock_uhome_api):
    h = AsyncPushUpdateHandler(hass, mock_uhome_api, entry_id="e1")

    with patch(
        "custom_components.u_tec.api.network.get_url",
        return_value="https://ha.example.com",
    ), patch(
        "custom_components.u_tec.api.webhook.async_generate_url",
        return_value="https://ha.example.com/api/webhook/x",
    ), patch(
        "custom_components.u_tec.api.webhook.async_register",
        return_value=lambda: None,
    ), patch(
        "custom_components.u_tec.api.async_track_time_interval",
        return_value=MagicMock(),
    ):
        result = await h.async_register_webhook(auth_data=MagicMock())

    assert result is True
    mock_uhome_api.set_push_status.assert_awaited_once()


async def test_register_fails_when_no_url_available(hass, mock_uhome_api):
    h = AsyncPushUpdateHandler(hass, mock_uhome_api, entry_id="e1")

    with patch(
        "custom_components.u_tec.api.network.get_url",
        side_effect=NoURLAvailableError(),
    ):
        result = await h.async_register_webhook(auth_data=MagicMock())

    assert result is False
    mock_uhome_api.set_push_status.assert_not_awaited()


async def test_register_falls_back_through_url_strategies(hass, mock_uhome_api):
    """First strategy fails, second succeeds — cloud fallback path."""
    h = AsyncPushUpdateHandler(hass, mock_uhome_api, entry_id="e1")

    call_count = [0]

    def _get_url(*args, **kwargs):
        call_count[0] += 1
        if call_count[0] == 1:
            raise NoURLAvailableError()
        return "https://cloud.example.com"

    with patch(
        "custom_components.u_tec.api.network.get_url", side_effect=_get_url,
    ), patch(
        "custom_components.u_tec.api.webhook.async_generate_url",
        return_value="https://cloud.example.com/api/webhook/x",
    ), patch(
        "custom_components.u_tec.api.webhook.async_register",
        return_value=lambda: None,
    ), patch(
        "custom_components.u_tec.api.async_track_time_interval",
        return_value=MagicMock(),
    ):
        result = await h.async_register_webhook(auth_data=MagicMock())

    assert result is True
    assert call_count[0] >= 2  # at least one fallback hit


async def test_register_fails_when_api_set_push_status_errors(hass, mock_uhome_api):
    from utec_py.exceptions import ApiError

    h = AsyncPushUpdateHandler(hass, mock_uhome_api, entry_id="e1")
    mock_uhome_api.set_push_status.side_effect = ApiError(500, "fail")

    with patch(
        "custom_components.u_tec.api.network.get_url",
        return_value="https://ha.example.com",
    ), patch(
        "custom_components.u_tec.api.webhook.async_generate_url",
        return_value="https://ha.example.com/api/webhook/x",
    ), patch(
        "custom_components.u_tec.api.async_track_time_interval",
        return_value=MagicMock(),
    ):
        result = await h.async_register_webhook(auth_data=MagicMock())

    assert result is False


# --- Secret rotation + unregister ---


async def test_register_generates_new_secret_each_call(hass, mock_uhome_api):
    h = AsyncPushUpdateHandler(hass, mock_uhome_api, entry_id="e1")

    with patch(
        "custom_components.u_tec.api.network.get_url",
        return_value="https://ha.example.com",
    ), patch(
        "custom_components.u_tec.api.webhook.async_generate_url",
        return_value="https://ha.example.com/api/webhook/x",
    ), patch(
        "custom_components.u_tec.api.webhook.async_register",
        return_value=lambda: None,
    ), patch(
        "custom_components.u_tec.api.async_track_time_interval",
        return_value=MagicMock(),
    ):
        await h.async_register_webhook(auth_data=MagicMock())
        first = h._push_secret
        await h.async_register_webhook(auth_data=MagicMock())
        second = h._push_secret

    assert first != second


async def test_unregister_cancels_reregister_and_unregisters_hook(hass, mock_uhome_api):
    h = AsyncPushUpdateHandler(hass, mock_uhome_api, entry_id="e1")
    h._unregister_webhook = MagicMock()
    cancel_mock = MagicMock()
    h._cancel_reregister = cancel_mock

    with patch(
        "custom_components.u_tec.api.webhook.async_unregister",
    ) as mock_unreg:
        await h.unregister_webhook()

    cancel_mock.assert_called_once()
    mock_unreg.assert_called_once()
    assert h._cancel_reregister is None
    assert h._unregister_webhook is None


async def test_unregister_noop_when_nothing_registered(hass, mock_uhome_api):
    h = AsyncPushUpdateHandler(hass, mock_uhome_api, entry_id="e1")
    # Neither _unregister_webhook nor _cancel_reregister is set — should not raise
    await h.unregister_webhook()
