"""Constants for the U-tec Integration."""
DOMAIN = "utec_integration"
MANUFACTURER = "U-Tec"
CONF_IMPLEMENTATION: Final = "implementation"

# OAuth2 related constants
AUTH_URL = "https://oauth.u-tec.com/authorize"
TOKEN_URL = "https://oauth.u-tec.com/token"

# Config flow constants
CONF_SCOPE = "openapi"  # Add scope constant

# Default scope for U-tec API
DEFAULT_SCOPE = "openapi"  # Update this with the correct scope

#Requests
API_URL = "https://api.u-tec.com/"