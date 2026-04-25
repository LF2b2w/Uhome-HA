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
    value = options.get(conf_key, DEFAULT_OPTIMISTIC)
    if isinstance(value, bool):
        return value
    return device_id in value
