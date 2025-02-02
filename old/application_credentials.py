from homeassistant.components.application_credentials import (
    AuthorizationServer,
    ClientCredential,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_entry_oauth2_flow

from .api import UtecAuth

AUTHORIZATION_SERVER = AuthorizationServer(
    UTEC_AUTH_URI, UTEC_TOKEN_URI
)

async def async_get_auth_implementation(
        hass: HomeAssistant, auth_domain: str, credential: ClientCredential
    ) -> config_entry_oauth2_flow.AbstractOauth2Implementation:
    """ Return auth implementation"""
    return UTecAuthentication(hass, auth_domain, credential, AUTHORIZATION_SERVER)

async def async_get_description_placeholders(hass: HomeAssistant) -> dict[str, str]:
    """Return description placeholders for credentials dialog"""
    return {
        "oauth_consent_url": {
            "Uhome API Consent"
        },
        "more_info_url": "github link",
        "oauth_creds_url": "Github readme",
    }