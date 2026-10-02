"""Optimistic-update configuration resolver.

Standalone module with no project or Home Assistant imports, so it can be
unit-tested without loading the integration package or Home Assistant.
"""

from __future__ import annotations

from typing import Any, Mapping

CONF_OPTIMISTIC_LIGHTS = "optimistic_lights"
CONF_OPTIMISTIC_SWITCHES = "optimistic_switches"
CONF_OPTIMISTIC_LOCKS = "optimistic_locks"
DEFAULT_OPTIMISTIC = True

CONF_ADAPTIVE_AGGRESSIVE_LOCKS = "adaptive_aggressive_locks"
# Off until configured. Recommended on for locks: U-Tec push is unreliable,
# and a short confirmation burst is safer than showing an unconfirmed state.
DEFAULT_ADAPTIVE_AGGRESSIVE = False


def option_enabled(
    options: Mapping[str, Any],
    conf_key: str,
    device_id: str,
    default: bool,
) -> bool:
    """Resolve a True / False / list[device_id] option for one device."""
    value = options.get(conf_key, default)
    if isinstance(value, bool):
        return value
    return device_id in value


def is_optimistic_enabled(
    options: Mapping[str, Any],
    conf_key: str,
    device_id: str,
) -> bool:
    """Return True if optimistic updates are enabled for this device.

    value shape:
      - absent  -> DEFAULT_OPTIMISTIC (True)
      - True    -> all devices of this type optimistic
      - False   -> no devices of this type optimistic
      - list    -> only listed device IDs optimistic
    """
    return option_enabled(options, conf_key, device_id, DEFAULT_OPTIMISTIC)


def is_adaptive_aggressive_enabled(
    options: Mapping[str, Any],
    device_id: str,
) -> bool:
    """Return True if Adaptive Aggressive polling is enabled for this lock.

    Same shape as the optimistic options: absent/False off, True all locks,
    list only the listed device IDs. Absent defaults to off.
    """
    return option_enabled(
        options,
        CONF_ADAPTIVE_AGGRESSIVE_LOCKS,
        device_id,
        DEFAULT_ADAPTIVE_AGGRESSIVE,
    )


def push_asserts_state(push_data: Any, capability: str, attribute: str) -> bool:
    """Return True if a push payload actually carries the given capability state.

    U-Tec pushes are full-state replaces (utec_py update_state_data assigns the
    payload wholesale), and the device accessors fall back to a default when a
    capability is absent -- e.g. Lock.is_locked and Switch.is_on both return
    False when their capability is missing, which is indistinguishable from a
    real "unlocked"/"off". A partial push (a door-sensor or battery event that
    omits the lock/switch state) would therefore read as an authoritative
    "off"/"unlocked" and wrongly clear optimistic state mid-command.

    push_data is the {capability: {attribute: value}} dict produced by
    device.get_state_data(); only treat a push as asserting the state when the
    relevant capability/attribute is actually present in it.
    """
    if not isinstance(push_data, dict):
        return False
    cap = push_data.get(capability)
    return isinstance(cap, dict) and attribute in cap
