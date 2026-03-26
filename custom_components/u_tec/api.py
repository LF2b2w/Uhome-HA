"""API for Uhome bound to Home Assistant OAuth."""

import json
import logging
import secrets
from datetime import timedelta

from aiohttp import ClientSession, web

from homeassistant.components import webhook
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import config_entry_oauth2_flow, network
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.network import NoURLAvailableError
from utec_py.api import AbstractAuth, UHomeApi
from utec_py.exceptions import ApiError, UHomeError

from .const import DOMAIN, WEBHOOK_HANDLER, WEBHOOK_ID_PREFIX

_LOGGER = logging.getLogger(__name__)

# Re-register the webhook with a fresh secret every 24 hours
_REREGISTER_INTERVAL = timedelta(hours=24)


class AsyncConfigEntryAuth(AbstractAuth):
    """Provide Uhome Oauth2 authentication tied to an OAuth2 based config entry."""

    def __init__(
        self,
        websession: ClientSession,
        oauth_session: config_entry_oauth2_flow.OAuth2Session,
    ) -> None:
        """Initialize Oauth2 auth."""
        super().__init__(websession)
        self._oauth_session = oauth_session

    async def async_get_access_token(self) -> str:
        """Return a valid access token."""
        await self._oauth_session.async_ensure_token_valid()
        return self._oauth_session.token["access_token"]


class AsyncPushUpdateHandler:
    """Handle webhook registration and processing for Uhome API."""

    def __init__(self, hass: HomeAssistant, api: UHomeApi, entry_id: str) -> None:
        """Initialize the webhook handler."""
        self.hass = hass
        self.entry_id = entry_id
        self.webhook_id = f"{WEBHOOK_ID_PREFIX}{entry_id}"
        self.webhook_url = None
        self._unregister_webhook = None
        self._cancel_reregister = None
        self._push_secret: str | None = None
        self.api = api
        self._auth_data = None

    def _generate_secret(self) -> str:
        """Generate a fresh random secret token for push validation."""
        return secrets.token_urlsafe(32)

    async def async_register_webhook(self, auth_data) -> bool:
        """Register webhook with Home Assistant and the Uhome API."""
        self._auth_data = auth_data

        # Try multiple URL resolution strategies
        external_url = None
        for allow_internal, allow_ip, prefer_cloud in [
            (False, False, False),
            (False, False, True),
            (True, True, False),
        ]:
            try:
                external_url = network.get_url(
                    self.hass,
                    allow_internal=allow_internal,
                    allow_ip=allow_ip,
                    prefer_cloud=prefer_cloud,
                )
                if external_url:
                    _LOGGER.debug(
                        "Resolved webhook base URL: %s (internal=%s, cloud=%s)",
                        external_url, allow_internal, prefer_cloud,
                    )
                    break
            except NoURLAvailableError:
                continue

        if not external_url:
            _LOGGER.error(
                "No external URL available for push notifications. "
                "Configure an external URL in Settings -> System -> Network, "
                "or enable Home Assistant Cloud (Nabu Casa)."
            )
            return False

        webhook_url = webhook.async_generate_url(self.hass, self.webhook_id)

        if any(local in webhook_url for local in (
            "192.168.", "10.", "172.", "homeassistant.local", "localhost", "127.0."
        )):
            _LOGGER.warning(
                "Webhook URL %s appears to be a local address. "
                "U-Tec's servers cannot reach it -- push state updates will not work. "
                "Set up Nabu Casa or an externally-reachable URL.",
                webhook_url,
            )

        # Generate a fresh secret for this registration
        self._push_secret = self._generate_secret()
        _LOGGER.debug("Generated new push secret for webhook registration")

        try:
            _LOGGER.debug("Registering webhook URL: %s", webhook_url)
            result = await self.api.set_push_status(webhook_url, self._push_secret)
            _LOGGER.debug("Webhook registration result: %s", result)
        except ApiError as err:
            _LOGGER.error("Failed to register webhook with U-Tec API: %s", err)
            return False

        # Register HA-side webhook handler (only once)
        if not self._unregister_webhook:
            self._unregister_webhook = webhook.async_register(
                self.hass,
                DOMAIN,
                WEBHOOK_HANDLER,
                self.webhook_id,
                self._handle_webhook,
            )

        self.webhook_url = webhook_url

        # Schedule daily re-registration with a fresh secret
        if self._cancel_reregister:
            self._cancel_reregister()
        self._cancel_reregister = async_track_time_interval(
            self.hass,
            self._async_reregister,
            _REREGISTER_INTERVAL,
        )
        _LOGGER.debug("Scheduled daily webhook re-registration")

        return True

    @callback
    def _async_reregister(self, _now) -> None:
        """Trigger webhook re-registration with a fresh secret (called by scheduler)."""
        _LOGGER.debug("Daily webhook re-registration triggered")
        self.hass.async_create_task(
            self.async_register_webhook(self._auth_data)
        )

    async def unregister_webhook(self) -> None:
        """Unregister the webhook and cancel the re-registration scheduler."""
        if self._cancel_reregister:
            self._cancel_reregister()
            self._cancel_reregister = None
        if self._unregister_webhook:
            webhook.async_unregister(self.hass, self.webhook_id)
            self._unregister_webhook = None
            _LOGGER.debug("Unregistered webhook %s", self.webhook_id)

    async def _handle_webhook(
        self, hass: HomeAssistant, webhook_id, request
    ) -> web.Response | None:
        """Handle webhook callback."""
        try:
            if request.method != "POST":
                _LOGGER.error("Unsupported method: %s", request.method)
                return web.Response(status=405)

            raw_body = await request.read()
            _LOGGER.debug(
                "Webhook hit received: method=%s headers=%s body=%s",
                request.method,
                dict(request.headers),
                raw_body.decode("utf-8", errors="replace"),
            )

            try:
                data = json.loads(raw_body)
            except Exception as json_err:  # noqa: BLE001
                _LOGGER.error("Failed to parse webhook JSON: %s", json_err)
                return web.Response(status=400)

            # Validate the push secret via the Authorization header.
            # U-Tec sends it as "Bearer <access_token>" in the HTTP header.
            if self._push_secret is not None:
                auth_header = request.headers.get("Authorization", "")
                incoming_token = auth_header.removeprefix("Bearer ").strip()
                if not incoming_token:
                    _LOGGER.warning(
                        "Webhook received with no Authorization header -- rejecting"
                    )
                    return web.Response(status=401)
                if not secrets.compare_digest(incoming_token, self._push_secret):
                    _LOGGER.error(
                        "Webhook received with invalid Bearer token -- rejecting"
                    )
                    return web.Response(status=403)

            _LOGGER.debug("Received webhook data: %s", data)

            if self.entry_id not in hass.data.get(DOMAIN, {}):
                _LOGGER.error("Unknown entry_id in webhook: %s", self.entry_id)
                return web.Response(status=404)

            coordinator = hass.data[DOMAIN][self.entry_id]["coordinator"]
            await coordinator.update_push_data(data)

        except UHomeError as err:
            _LOGGER.error("Error processing webhook: %s", err)
            return web.json_response({"success": False, "error": str(err)}, status=400)
        except Exception as err:  # noqa: BLE001
            _LOGGER.exception("Unexpected error processing webhook: %s", err)
            return web.json_response({"success": False, "error": "Internal error"}, status=500)
        else:
            return web.json_response({"success": True})
