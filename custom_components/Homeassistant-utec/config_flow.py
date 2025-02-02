"""Config flow"""
from homeassistant import config_entries
from homeassistant.helpers import config_entry_oauth2_flow
from .const import DOMAIN

class UtecOAuth2FlowHandler(
    config_entries.ConfigFlow,
    domain=DOMAIN
):
    """Handle OAuth2 config flow."""
    # Implementation of OAuth2 flow with application credentials