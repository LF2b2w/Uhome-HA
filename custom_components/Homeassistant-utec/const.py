"""Constants for the U-tec Integration."""
DOMAIN = "utec_integration"

# OAuth2 related constants
OAUTH2_AUTHORIZE = "https://oauth.u-tec.com/authorize"
OAUTH2_TOKEN = "https://oauth.u-tec.com/token"

# Config flow constants
CONF_CLIENT_ID = "client_id"
CONF_CLIENT_SECRET = "client_secret"
CONF_SCOPE = "scope"  # Add scope constant

# Default scope for U-tec API
DEFAULT_SCOPE = "user"  # Update this with the correct scope

#Requests
REQ_URL = "https://api.u-tec.com/action"