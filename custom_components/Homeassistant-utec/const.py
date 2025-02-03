# const.py
"""Constants for the Utec integration."""
from enum import Enum
from typing import TypedDict, Optional
DOMAIN = "utec"

# OAuth2 endpoints
OAUTH2_AUTHORIZE = "https://auth.utec.com/oauth2/authorize"
OAUTH2_TOKEN = "https://auth.utec.com/oauth2/token"
API_BASE_URL = "https://api.utec.com"

# Configuration
CONF_CLIENT_ID = "client_id"
CONF_CLIENT_SECRET = "client_secret"

# Device Attributes
ATTR_HANDLE_TYPE = "handleType"
ATTR_DEVICE_ID = "id"
ATTR_NAME = "name"
ATTR_CATEGORY = "category"
ATTR_DEVICE_INFO = "deviceInfo"
ATTR_ATTRIBUTES = "attributes"

## D
class ApiNamespace(str, Enum):
    DEVICE = "Uhome.Device"
    USER = "Uhome.User"

class ApiOperation(str, Enum):
    DISCOVERY = "Discovery"
    QUERY = "Query"
    COMMAND = "Command"

class ApiHeader(TypedDict):
    namespace: str
    name: str
    messageID: str
    payloadVersion: str

class ApiRequest(TypedDict):
    header: ApiHeader
    payload: Optional[dict]