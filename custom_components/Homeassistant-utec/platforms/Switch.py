from homeassistant.components.switch import SwitchEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from ..const import DOMAIN

class UHomeSwitch(CoordinatorEntity, SwitchEntity):
    """Representation of a U-Home Switch."""

    def __init__(self, coordinator, device_id):
        """Initialize the switch entity."""
        super().__init__(coordinator)
        self.device_id = device_id
        self._device = coordinator.get_device(device_id)

    @property
    def unique_id(self):
        """Return a unique ID for the switch."""
        return f"{DOMAIN}_switch_{self.device_id}"

    @property
    def name(self):
        """Return the name of the switch."""
        return self._device._name

    @property
    def is_on(self):
        """Return true if the switch is on."""
        return self._device.is_on

    @property
    def device_info(self):
        """Return device information for the switch."""
        return self.coordinator.get_ha_device_info(self._device)

    async def async_turn_on(self, **kwargs):
        """Turn on the switch."""
        await self.coordinator.async_send_command(self.device_id, "turn_on")

    async def async_turn_off(self, **kwargs):
        """Turn off the switch."""
        await self.coordinator.async_send_command(self.device_id, "turn_off")

    async def async_update(self):
        """Update the switch state."""
        await self.coordinator.async_request_refresh()