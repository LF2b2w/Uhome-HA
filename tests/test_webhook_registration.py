"""Tests for AsyncPushUpdateHandler.async_register_webhook — URL resolution."""

from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.helpers.network import NoURLAvailableError
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.u_tec.api import AsyncPushUpdateHandler


def _patch_no_cloud():
    """Disable the cloudhook path so tests exercise network.get_url fallbacks."""
    return patch(
        "custom_components.u_tec.api.cloud.async_active_subscription",
        return_value=False,
    )


async def test_register_succeeds_with_external_url(hass, mock_uhome_api):
    h = AsyncPushUpdateHandler(hass, mock_uhome_api, entry_id="e1")

    with _patch_no_cloud(), patch(
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
    assert h._used_cloudhook is False


async def test_register_prefers_cloudhook_when_cloud_active(hass, mock_uhome_api):
    """Nabu Casa active → use cloudhook, skip network.get_url."""
    h = AsyncPushUpdateHandler(hass, mock_uhome_api, entry_id="e1")
    cloudhook_url = "https://hooks.nabu.casa/abc123"

    with patch(
        "custom_components.u_tec.api.cloud.async_active_subscription",
        return_value=True,
    ), patch(
        "custom_components.u_tec.api.cloud.async_get_or_create_cloudhook",
        new_callable=AsyncMock,
        return_value=cloudhook_url,
    ) as mock_cloudhook, patch(
        "custom_components.u_tec.api.network.get_url",
    ) as mock_get_url, patch(
        "custom_components.u_tec.api.webhook.async_register",
        return_value=None,
    ), patch(
        "custom_components.u_tec.api.async_track_time_interval",
        return_value=MagicMock(),
    ):
        result = await h.async_register_webhook(auth_data=MagicMock())

    assert result is True
    mock_cloudhook.assert_awaited_once_with(hass, h.webhook_id)
    mock_get_url.assert_not_called()
    mock_uhome_api.set_push_status.assert_awaited_once()
    assert mock_uhome_api.set_push_status.await_args.args[0] == cloudhook_url
    assert h._used_cloudhook is True
    assert h.webhook_url == cloudhook_url


async def test_register_falls_back_when_cloudhook_fails(hass, mock_uhome_api):
    """Cloudhook creation error → fall back to network.get_url."""
    h = AsyncPushUpdateHandler(hass, mock_uhome_api, entry_id="e1")

    with patch(
        "custom_components.u_tec.api.cloud.async_active_subscription",
        return_value=True,
    ), patch(
        "custom_components.u_tec.api.cloud.async_get_or_create_cloudhook",
        new_callable=AsyncMock,
        side_effect=RuntimeError("cloud unavailable"),
    ), patch(
        "custom_components.u_tec.api.network.get_url",
        return_value="https://ha.example.com",
    ), patch(
        "custom_components.u_tec.api.webhook.async_generate_url",
        return_value="https://ha.example.com/api/webhook/x",
    ), patch(
        "custom_components.u_tec.api.webhook.async_register",
        return_value=None,
    ), patch(
        "custom_components.u_tec.api.async_track_time_interval",
        return_value=MagicMock(),
    ):
        result = await h.async_register_webhook(auth_data=MagicMock())

    assert result is True
    assert h._used_cloudhook is False
    mock_uhome_api.set_push_status.assert_awaited_once()


async def test_register_fails_when_no_url_available(hass, mock_uhome_api):
    h = AsyncPushUpdateHandler(hass, mock_uhome_api, entry_id="e1")

    with _patch_no_cloud(), patch(
        "custom_components.u_tec.api.network.get_url",
        side_effect=NoURLAvailableError("no external URL configured"),
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
            raise NoURLAvailableError("first strategy unavailable")
        return "https://cloud.example.com"

    with _patch_no_cloud(), patch(
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

    with _patch_no_cloud(), patch(
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

    with _patch_no_cloud(), patch(
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


async def test_register_twice_does_not_re_register_handler(hass, mock_uhome_api):
    """webhook.async_register returns None — guard must still skip on second call.

    Regression: storing the None return value as the "registered" flag broke the
    guard, so the next call (e.g. the 24h re-register timer) re-entered the
    block and webhook.async_register raised ValueError("Handler is already defined!").
    """
    h = AsyncPushUpdateHandler(hass, mock_uhome_api, entry_id="e1")

    with _patch_no_cloud(), patch(
        "custom_components.u_tec.api.network.get_url",
        return_value="https://ha.example.com",
    ), patch(
        "custom_components.u_tec.api.webhook.async_generate_url",
        return_value="https://ha.example.com/api/webhook/x",
    ), patch(
        "custom_components.u_tec.api.webhook.async_register",
        return_value=None,
    ) as mock_register, patch(
        "custom_components.u_tec.api.async_track_time_interval",
        return_value=MagicMock(),
    ):
        await h.async_register_webhook(auth_data=MagicMock())
        await h.async_register_webhook(auth_data=MagicMock())

    assert mock_register.call_count == 1


async def test_24h_reregister_timer_does_not_raise(hass, mock_uhome_api):
    """Advance time by 24h and verify the re-register timer fires cleanly.

    Before the fix, the scheduled _async_reregister callback would call
    webhook.async_register again (because the guard's flag had been set to None),
    raising ValueError("Handler is already defined!"). With the boolean-flag
    fix, the guard correctly skips re-registration on the second cycle.
    """
    h = AsyncPushUpdateHandler(hass, mock_uhome_api, entry_id="e1")

    with _patch_no_cloud(), patch(
        "custom_components.u_tec.api.network.get_url",
        return_value="https://ha.example.com",
    ), patch(
        "custom_components.u_tec.api.webhook.async_generate_url",
        return_value="https://ha.example.com/api/webhook/x",
    ), patch(
        "custom_components.u_tec.api.webhook.async_register",
        return_value=None,
    ) as mock_register, patch(
        "custom_components.u_tec.api.webhook.async_unregister",
    ):
        # Real async_track_time_interval scheduler — no mock — so the 24h timer
        # actually arms.
        await h.async_register_webhook(auth_data=MagicMock())

        # 24h + 1 minute later, the daily re-register callback fires.
        async_fire_time_changed(hass, dt_util.utcnow() + timedelta(hours=24, minutes=1))
        await hass.async_block_till_done()

        # Exactly one HA-side registration despite the timer cycling. If the
        # guard were broken, this would be 2 and the second call would raise.
        assert mock_register.call_count == 1
        # set_push_status fires for both the initial and the daily re-register —
        # confirms the timer callback actually ran (the test would otherwise
        # silently pass because the timer was never scheduled).
        assert mock_uhome_api.set_push_status.await_count == 2

        # Clean up the (now re-armed) timer so the lingering-timer guard in
        # pytest-homeassistant-custom-component's teardown doesn't fail us.
        await h.unregister_webhook()
