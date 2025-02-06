"""Siwtch device for U-tec integration."""

from utec_py_LF2b2w.devices.switch import UtecSwitch
from voluptuous import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import UHomeDeviceCoordinator, UtecEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up U-tec switch devices."""
    coordinator: UHomeDeviceCoordinator = hass.data[DOMAIN][entry.entry_id]

    switches = []
    for device_id in coordinator.devices_ids:
        device = await coordinator.get_device(device_id)
        if device.type == "switch":
            switches.append(Uhomeswitch(coordinator, device_id))

    async_add_entities(switches)


class Uhomeswitch(UtecEntity, SwitchEntity):
    """Representation of a U-tec Smart Switch."""

    def __init__(self, coordinator: UHomeDeviceCoordinator, device_id: str) -> None:
        """Initialize the switch."""
        super().__init__(coordinator, device_id)
        self._attr_name = coordinator.data[device_id]["name"]
        self._attr_unique_id = device_id

    @property
    def is_on(self) -> bool:
        """Return true if the switch is on."""
        return self.coordinator.data[self._device_id]["state"].get("on", False)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the switch on."""
        await UtecSwitch.turn_on()
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the switch off."""
        await UtecSwitch.turn_off()
        await self.coordinator.async_request_refresh()

    async def async_update(self) -> None:
        """Fetch new state data for the switch."""
        self._device.update_state()
