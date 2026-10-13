"""Helpers for interpreting normalized lock state payloads."""

from __future__ import annotations

from typing import Any

LOCK_CAPABILITY = "st.lock"
LOCK_ATTRIBUTE = "lockState"


def reported_locked(state_data: Any) -> bool | None:
    """Return a recognized lock state from a normalized capability mapping.

    Raw U-Tec ``states`` records are intentionally not accepted here; callers
    must use the normalized payload produced by the device client.
    """
    if not isinstance(state_data, dict):
        return None
    capability = state_data.get(LOCK_CAPABILITY)
    if not isinstance(capability, dict) or LOCK_ATTRIBUTE not in capability:
        return None
    value = capability[LOCK_ATTRIBUTE]
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.lower()
        if normalized == "locked":
            return True
        if normalized == "unlocked":
            return False
    return None
