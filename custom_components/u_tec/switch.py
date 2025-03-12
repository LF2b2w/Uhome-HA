"""Support for Uhome switches."""

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import _LOGGER, HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from utec_py.devices.switch import Switch as UhomeSwitch
from utec_py.exceptions import DeviceError

from .const import DOMAIN
from .coordinator import UhomeDataUpdateCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Uhome switch based on a config entry."""
    coordinator: UhomeDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id][
        "coordinator"
    ]

    async_add_entities(
        UhomeSwitchEntity(coordinator, device_id)
        for device_id, device in coordinator.devices.items()
        if isinstance(device, UhomeSwitch)
    )


class UhomeSwitchEntity(CoordinatorEntity, SwitchEntity):
    """Representation of a Uhome switch."""

    def __init__(self, coordinator: UhomeDataUpdateCoordinator, device_id: str) -> None:
        """Initialize the switch."""
        super().__init__(coordinator)
        self._device = coordinator.devices[device_id]
        self._attr_unique_id = f"{DOMAIN}_{device_id}"
        self._attr_name = self._device.name
        self._attr_device_info = self._device.device_info
        self._attr_has_entity_name = True

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self.coordinator.last_update_success and self._device.available

    @property
    def is_on(self) -> bool:
        """Return true if switch is on."""
        return self._device.is_on

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the switch on."""
        try:
            await self._device.turn_on()
            await self.coordinator.async_request_refresh()
        except DeviceError as err:
            _LOGGER.error(
                "Failed to turn on switch %s: %s", self._device.device_id, err
            )
            raise HomeAssistantError(f"Failed to turn on switch: {err}") from err

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the switch off."""
        try:
            await self._device.turn_off()
            await self.coordinator.async_request_refresh()
        except DeviceError as err:
            _LOGGER.error(
                "Failed to turn off switch %s: %s", self._device.device_id, err
            )
            raise HomeAssistantError(f"Failed to turn off switch: {err}") from err
