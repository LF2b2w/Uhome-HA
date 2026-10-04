"""Shared entity helpers."""

from homeassistant.helpers.entity import DeviceInfo

from .const import DOMAIN


def hub_device_info(coordinator) -> DeviceInfo:
    """The account-level "U-Tec Integration" device.

    Holds the entities that describe the integration itself rather than a
    physical device: Last Push, API accounting, and Debug Polling Mode.
    """
    entry_id = coordinator.config_entry.entry_id
    return DeviceInfo(
        identifiers={(DOMAIN, f"{entry_id}_service")},
        name="U-Tec Integration",
        manufacturer="U-Tec",
    )
