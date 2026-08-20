"""Constants for the Uhome integration."""

from datetime import timedelta

from .optimistic import (
    CONF_OPTIMISTIC_LIGHTS,
    CONF_OPTIMISTIC_SWITCHES,
    CONF_OPTIMISTIC_LOCKS,
    DEFAULT_OPTIMISTIC,
    is_optimistic_enabled,
    push_asserts_state,
)

DOMAIN = "u_tec"

# Bound how long an unconfirmed optimistic state may override the device's
# reported state, shared by lock/light/switch. Without it, a command the
# device never fulfils (a lock auto-locking after an unlock, a switch command
# that silently fails) pins the entity permanently. ~3 polls at the default
# 10s scan interval preserves the grace period while the device physically
# settles, then defers to the device.
# https://github.com/LF2b2w/Uhome-HA/issues/58
OPTIMISTIC_TIMEOUT = timedelta(seconds=30)

# How many consecutive coordinator poll failures are allowed before entities
# report unavailable. One failure is treated as a transient blip; two in a
# row (or a device that reports offline) marks entities unavailable.
# Auth failures immediately set the counter to this threshold.
MAX_CONSECUTIVE_UPDATE_FAILURES = 2

CONF_SCAN_INTERVAL = "scan_interval"
CONF_DISCOVERY_INTERVAL = "discovery_interval"

DEFAULT_SCAN_INTERVAL = 10  # seconds
DEFAULT_DISCOVERY_INTERVAL = 300  # seconds (5 minutes)
MIN_SCAN_INTERVAL = 10
MAX_SCAN_INTERVAL = 3600

# Key used inside hass.data[DOMAIN] for yaml-sourced config (separate from entry IDs).
YAML_CONFIG_KEY = "_yaml_config"

OAUTH2_AUTHORIZE = "https://oauth.u-tec.com/authorize"
OAUTH2_TOKEN = "https://oauth.u-tec.com/token"

CONF_PUSH_ENABLED = "push_enabled"
CONF_PUSH_DEVICES = "push_devices"
CONF_HA_DEVICES = "HomeAssistant_devices"
DEFAULT_API_SCOPE = "openapi"

API_BASE_URL = "https://api.u-tec.com/action"

SIGNAL_NEW_DEVICE = f"{DOMAIN}_new_device"
SIGNAL_DEVICE_UPDATE = f"{DOMAIN}_device_update"

WEBHOOK_ID_PREFIX = "u_tec_push_"
WEBHOOK_HANDLER = 'u_tec_webhook_handler'
