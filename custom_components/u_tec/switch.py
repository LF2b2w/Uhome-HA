"""Support for Uhome switches."""

from typing import Any

from utec_py.devices.switch import Switch as UhomeSwitch

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import UhomeDataUpdateCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Uhome switch based on a config entry."""
    coordinator: UhomeDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]

    async_add_entities(
        UhomeSwitchEntity(coordinator, device_id)
        for device_id, device in coordinator.devices.items()
        if isinstance(device, UhomeSwitch)
    )


class UhomeSwitchEntity(CoordinatorEntity, SwitchEntity):
    """Representation of a UUhometec switch."""

    def __init__(self, coordinator: UhomeDataUpdateCoordinator, device_id: str) -> None:
        """Initialize the switch."""
        super().__init__(coordinator)
        self._device = coordinator.devices[device_id]
        self._attr_unique_id = f"{DOMAIN}_{device_id}"
        self._attr_name = self._device.name
        self._attr_device_info = self._device.device_info

    @property
    def is_on(self) -> bool:
        """Return true if switch is on."""
        return self._device.is_on

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self._device.available

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the switch on."""
        await self._device.turn_on()
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the switch off."""
        await self._device.turn_off()
        await self.coordinator.async_request_refresh()
