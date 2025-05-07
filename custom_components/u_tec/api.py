"""API for Uhome bound to Home Assistant OAuth."""

import logging
from xml.dom import ValidationErr

from aiohttp import ClientSession

from homeassistant.components import webhook
from homeassistant.helpers import network
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import config_entry_oauth2_flow
from utec_py.api import AbstractAuth, UHomeApi
from utec_py.exceptions import ApiError, UHomeError, ValidationError

from .const import DOMAIN, WEBHOOK_HANDLER, WEBHOOK_ID_PREFIX

_LOGGER = logging.getLogger(__name__)


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
        if self._oauth_session.valid_token is None:
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
        self.api = api

    async def async_register_webhook(self, auth_data) -> bool:
        """Register webhook with Home Assistant and the Uhome API."""
        
        # Get the external URL
        external_url = network.get_url(self.hass, prefer_external=True)
        if not external_url:
            _LOGGER.error(
                "External URL not configured, push notifications will not work"
            )
            return False
        if external_url:
            webhook_url = webhook.async_generate_url(self.hass, self.webhook_id)
        else:
            raise ValidationError

        # Register the webhook with the API
        access_token = await auth_data.async_get_access_token()
        try:
            _LOGGER.debug("Registering webhook URL:%s", webhook_url)
            result = await self.api.set_push_status(access_token, webhook_url)
            _LOGGER.debug("Webhook registration result: %s", result)
        except ApiError as err:
            _LOGGER.error("Failed to register webhook: %s", err)
            return False
        else:
            # Register webhook handler in Home Assistant
            self._unregister_webhook = webhook.async_register(
                self.hass, 
                DOMAIN, 
                WEBHOOK_HANDLER, 
                self.webhook_id, 
                self._handle_webhook
            )
            return True

    def unregister_webhook(self) -> None:
        """Unregister the webhook."""
        if self._unregister_webhook:
            #self._unregister_webhook()
            webhook.async_unregister(self.hass, self.webhook_id)
            self._unregister_webhook = None
            _LOGGER.debug("Unregistered webhook %s", self.webhook_id)

    @callback
    async def _handle_webhook(self, hass: HomeAssistant, webhook_id, request):
        """Handle webhook callback."""
        try:
            # Handle POST request
            if request.method != "POST":
                _LOGGER.error("Unsupported method: %s", request.method)
                return None

            data = await request.json()
            _LOGGER.debug("Received webhook data: %s", data)

            if self.entry_id not in hass.data[DOMAIN]:
                _LOGGER.error("Unknown entry_id in webhook: %s", self.entry_id)
                return None

            coordinator = hass.data[DOMAIN][self.entry_id]["coordinator"]

            # Process the device update
            await coordinator.update_push_data(data)

        except UHomeError as err:
            _LOGGER.error("Error processing webhook: %s", err)
            return {"success": False, "error": str(err)}
        else:
            return {"success": True}
