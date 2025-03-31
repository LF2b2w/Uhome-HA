"""Constants for the Uhome integration."""

DOMAIN = "u_tec"

OAUTH2_AUTHORIZE = "https://oauth.u-tec.com/authorize"
OAUTH2_TOKEN = "https://oauth.u-tec.com/token"

CONF_API_SCOPE = "scope"
CONF_PUSH_ENABLED = "push_enabled"
CONF_PUSH_DEVICES = "push_devices"
CONF_HA_DEVICES = "HomeAssistant_devices"
DEFAULT_API_SCOPE = "openapi"

API_BASE_URL = "https://api.u-tec.com/action"

SIGNAL_NEW_DEVICE = f"{DOMAIN}_new_device"
SIGNAL_DEVICE_UPDATE = f"{DOMAIN}_device_update"

WEBHOOK_ID_PREFIX = "u_tec_push_"
WEBHOOK_HANDLER = 'u_tec_webhook_handler'
