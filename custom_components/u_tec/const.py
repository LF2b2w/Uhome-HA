"""Constants for the Uhome integration."""

from datetime import timedelta

from .optimistic import (
    CONF_ADAPTIVE_AGGRESSIVE_LOCKS,
    CONF_OPTIMISTIC_LIGHTS,
    CONF_OPTIMISTIC_SWITCHES,
    CONF_OPTIMISTIC_LOCKS,
    DEFAULT_ADAPTIVE_AGGRESSIVE,
    DEFAULT_OPTIMISTIC,
    is_adaptive_aggressive_enabled,
    is_optimistic_enabled,
    push_asserts_state,
)

DOMAIN = "u_tec"

# Bound how long an unconfirmed optimistic state may override the device's
# reported state, shared by lock/light/switch. Without it, a command the
# device never fulfils (a lock auto-locking after an unlock, a switch command
# that silently fails) pins the entity permanently. 1.5 polls at the default
# 20s scan interval (3 at the 10s floor) preserves the grace period while the device physically
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

DEFAULT_SCAN_INTERVAL = 20  # seconds
DEFAULT_DISCOVERY_INTERVAL = 300  # seconds (5 minutes)
# Normal-operation floor. Every install shares one vendor API that publishes
# no rate limits, so sub-10s polling is only available through Debug Polling
# Mode below, which is time-boxed and never saved.
MIN_SCAN_INTERVAL = 10
MAX_SCAN_INTERVAL = 3600

# Debug Polling Mode. A button or service polls at DEBUG_POLL_INTERVAL for at
# most DEBUG_POLL_DURATION, then the configured interval comes back. These are
# deliberately not options: the session is never saved, and pressing again
# while a session is active does not extend it.
DEBUG_POLL_INTERVAL = 1  # seconds
DEBUG_POLL_DURATION = 120  # seconds

# Before skipping a lock command because the cached lock mode says Passage,
# one fresh single-device query must confirm it. If it does not answer in
# this many seconds, the command is sent anyway: when in doubt, send it.
PASSAGE_VERIFY_TIMEOUT = 10  # seconds

# Adaptive Aggressive lock confirmation. After a lock/unlock command, poll
# that one device on this schedule until the API reports the commanded state:
# four quick 1s checks while the bolt moves, then easing into Fibonacci so a
# slow cloud round trip is still caught without hammering. Bounded: at most
# len(ADAPTIVE_AGGRESSIVE_DELAYS) polls (about 35s), never a delay >= the idle
# scan interval, and it stops on the poll-failure threshold.
ADAPTIVE_AGGRESSIVE_DELAYS: tuple[int, ...] = (1, 1, 1, 1, 2, 3, 5, 8, 13)
ADAPTIVE_AGGRESSIVE_INITIAL_DELAY = ADAPTIVE_AGGRESSIVE_DELAYS[0]
ADAPTIVE_AGGRESSIVE_MAX_ATTEMPTS = len(ADAPTIVE_AGGRESSIVE_DELAYS)
# A confirmed state is protected for one idle interval, never longer than this.
CONFIRMATION_WINDOW_CAP = 60

# Key used inside hass.data[DOMAIN] for yaml-sourced config (separate from entry IDs).
YAML_CONFIG_KEY = "_yaml_config"
SERVICE_START_DEBUG_POLLING = "start_debug_polling"
SERVICE_STOP_DEBUG_POLLING = "stop_debug_polling"

OAUTH2_AUTHORIZE = "https://oauth.u-tec.com/authorize"
OAUTH2_TOKEN = "https://oauth.u-tec.com/token"

CONF_PUSH_ENABLED = "push_enabled"
CONF_PUSH_DEVICES = "push_devices"
CONF_HA_DEVICES = "HomeAssistant_devices"
DEFAULT_API_SCOPE = "openapi"

API_BASE_URL = "https://api.u-tec.com/action"

SIGNAL_NEW_DEVICE = f"{DOMAIN}_new_device"
SIGNAL_DEVICE_UPDATE = f"{DOMAIN}_device_update"
# Burst polls are not pushes. Listeners must not clear optimistic state
# immediately when this fires; that grace stays on the coordinator path.
SIGNAL_ADAPTIVE_POLL = f"{DOMAIN}_adaptive_poll"
EVENT_LOCK_COMMAND_FAILED = f"{DOMAIN}_lock_command_failed"

WEBHOOK_ID_PREFIX = "u_tec_push_"
WEBHOOK_HANDLER = 'u_tec_webhook_handler'
