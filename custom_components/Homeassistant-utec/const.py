"""Constants for the U-tec Integration."""
DOMAIN = "utec_integration"

# OAuth2 related constants
AUTH_URL = "https://oauth.u-tec.com/authorize"
TOKEN_URL = "https://oauth.u-tec.com/token"

# Config flow constants
CLIENT_ID = "8a925dfca69c23e40617c8cb27cb71e1"
CLIENT_SECRET = "f4309a770ec8983d7d0535cf5a7a817f"
CONF_SCOPE = "openapi"  # Add scope constant

# Default scope for U-tec API
DEFAULT_SCOPE = "user"  # Update this with the correct scope

#Requests
API_URL = "https://api.u-tec.com/"