"""Tests for AsyncPushUpdateHandler._handle_webhook (security boundary)."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from aiohttp import web

from custom_components.u_tec.api import AsyncPushUpdateHandler
from custom_components.u_tec.const import DOMAIN


def _make_request(method: str = "POST", *, body: bytes = b"{}", headers: dict | None = None):
    req = MagicMock()
    req.method = method
    req.read = AsyncMock(return_value=body)
    req.headers = headers or {}
    return req


@pytest.fixture
def webhook_handler(hass, mock_uhome_api):
    h = AsyncPushUpdateHandler(hass, mock_uhome_api, entry_id="entry-1")
    h._push_secret = "correct-secret"
    # Wire up hass.data so _handle_webhook can find the coordinator
    coord = MagicMock()
    coord.update_push_data = AsyncMock()
    hass.data[DOMAIN] = {"entry-1": {"coordinator": coord}}
    return h, coord


async def test_rejects_non_post_method(webhook_handler, hass):
    h, _ = webhook_handler
    resp = await h._handle_webhook(hass, "wh-id", _make_request("GET"))
    assert resp.status == 405


async def test_rejects_invalid_json_body(webhook_handler, hass):
    h, _ = webhook_handler
    req = _make_request(body=b"not-json")
    resp = await h._handle_webhook(hass, "wh-id", req)
    assert resp.status == 400


async def test_rejects_missing_authorization_header(webhook_handler, hass):
    h, _ = webhook_handler
    req = _make_request(body=b'{"devices": []}')
    resp = await h._handle_webhook(hass, "wh-id", req)
    assert resp.status == 401


async def test_rejects_wrong_bearer_token(webhook_handler, hass):
    h, _ = webhook_handler
    req = _make_request(
        body=b'{"devices": []}',
        headers={"Authorization": "Bearer wrong-secret"},
    )
    resp = await h._handle_webhook(hass, "wh-id", req)
    assert resp.status == 403


async def test_accepts_correct_bearer_token(webhook_handler, hass):
    h, coord = webhook_handler
    req = _make_request(
        body=b'{"payload": {"devices": []}}',
        headers={"Authorization": "Bearer correct-secret"},
    )
    resp = await h._handle_webhook(hass, "wh-id", req)
    assert resp.status == 200
    coord.update_push_data.assert_awaited_once()


async def test_rejects_unknown_entry_id(hass, mock_uhome_api):
    h = AsyncPushUpdateHandler(hass, mock_uhome_api, entry_id="bogus")
    h._push_secret = "s"
    hass.data[DOMAIN] = {}  # entry-1 not present
    req = _make_request(
        body=b'{"devices": []}',
        headers={"Authorization": "Bearer s"},
    )
    resp = await h._handle_webhook(hass, "wh-id", req)
    assert resp.status == 404


async def test_bearer_stripped_with_whitespace(webhook_handler, hass):
    h, coord = webhook_handler
    req = _make_request(
        body=b'{"payload": {"devices": []}}',
        headers={"Authorization": "Bearer   correct-secret  "},
    )
    resp = await h._handle_webhook(hass, "wh-id", req)
    assert resp.status == 200


async def test_no_push_secret_set_bypasses_token_check(hass, mock_uhome_api):
    """If _push_secret is None the handler doesn't validate the token."""
    h = AsyncPushUpdateHandler(hass, mock_uhome_api, entry_id="entry-1")
    h._push_secret = None
    coord = MagicMock()
    coord.update_push_data = AsyncMock()
    hass.data[DOMAIN] = {"entry-1": {"coordinator": coord}}

    req = _make_request(body=b'{"devices": []}')  # no auth header
    resp = await h._handle_webhook(hass, "wh-id", req)
    assert resp.status == 200
