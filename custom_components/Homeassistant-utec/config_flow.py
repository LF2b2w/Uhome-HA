"""Config flow for U-tec Integration."""
import logging
from typing import Any, Dict, Optional
from urllib.parse import urlencode
import webbrowser

from homeassistant import config_entries # type: ignore
from homeassistant.core import callback # type: ignore
from homeassistant.data_entry_flow import FlowResult # type: ignore

from .const import (
    DOMAIN,
    AUTH_URL,
    CLIENT_ID,
    CLIENT_SECRET,
    SCOPE,
)

_LOGGER = logging.getLogger(__name__)

class UtecConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle U-tec config flow."""

    VERSION = 1

    def __init__(self):
        """Initialize flow."""
        self.auth_url = None

async def async_step_user(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> FlowResult:
        """Handle a flow initialized by the user."""
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")

        # Generate OAuth URL with static credentials
        params = {
            "response_type": "code",
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "scope": SCOPE,
            "redirect_uri": f"{self.hass.config.external_url}/auth/external/callback",
            "state": self._async_generate_state(),
        }

        auth_url = f"{AUTH_URL}?{urlencode(params)}"

        # Open OAuth URL in default browser
        webbrowser.open(auth_url)

        # Return placeholder entry while waiting for callback
        return self.async_show_progress(
            step_id="auth",
            description_placeholders={
                "auth_url": auth_url,
            },
        )

async def async_step_auth(self, user_input: Optional[Dict[str, Any]] = None) -> FlowResult:
        """Handle oauth callback."""
        # This will be called by Home Assistant with the authorization code
        if not user_input:
            return self.async_show_progress_done(next_step_id="auth")

        return self.async_create_entry(
            title="U-tec Integration",
            data={
                "access_token": user_input.get("code"),
                "client_id": CLIENT_ID,
                "client_secret": CLIENT_SECRET,
            },
        )

def _async_generate_state(self) -> str:
        """Generate a random state string."""
        from secrets import token_urlsafe
        return token_urlsafe(32)