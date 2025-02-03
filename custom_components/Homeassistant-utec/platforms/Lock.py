from homeassistant.components.light import LightEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from ..const import DOMAIN

class UHomeLight(CoordinatorEntity, LightEntity):
    """Representation of a U-Home Light."""

    def __init__(self, coordinator, device_id):
        """Initialize the light entity."""
        super().__init__(coordinator)
        self.device_id = device_id
        self._device = coordinator.get_device(device_id)

    @property
    def unique_id(self):
        """Return a unique ID for the light."""
        return f"{DOMAIN}_light_{self.device_id}"

    @property
    def name(self):
        """Return the name of the light."""
        return self._device._name

    @property
    def is_on(self):
        """Return true if the light is on."""
        return self._device.is_on

    @property
    def brightness(self):
        """Return the brightness of the light."""
        return self._device.brightness

    @property
    def device_info(self):
        """Return device information for the light."""
        return self.coordinator.get_ha_device_info(self._device)

    async def async_turn_on(self, **kwargs):
        """Turn on the light."""
        brightness = kwargs.get("brightness")
        if brightness:
            await self.coordinator.async_send_command(
                self.device_id, "set_brightness", brightness=brightness
            )
        else:
            await self.coordinator.async_send_command(self.device_id, "turn_on")

    async def async_turn_off(self, **kwargs):
        """Turn off the light."""
        await self.coordinator.async_send_command(self.device_id, "turn_off")

    async def async_update(self):
        """Update the light state."""
        await self.coordinator.async_request_refresh()