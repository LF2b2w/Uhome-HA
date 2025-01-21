"""Constants for the U-tec Integration."""
DOMAIN = "utec_integration"

# OAuth2 related constants
AUTH_URL = "https://oauth.u-tec.com/authorize"
TOKEN_URL = "https://oauth.u-tec.com/token"

# Config flow constants
CLIENT_ID = "client_id"
CLIENT_SECRET = "client_secret"
CONF_SCOPE = "scope"  # Add scope constant

# Default scope for U-tec API
DEFAULT_SCOPE = "user"  # Update this with the correct scope

#Requests
API_URL = "https://api.u-tec.com/"