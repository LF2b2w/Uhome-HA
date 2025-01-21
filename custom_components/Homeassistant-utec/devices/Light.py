from homeassistant.components.light import LightEntity
from entity import UtecBaseEntity
from discovery.requests import DeviceCapability, DeviceCommand

class UtecLight(UtecBaseEntity, LightEntity):
    """Representation of a U-tec light."""

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the light on."""
        if DeviceCapability.SWITCH not in self.capabilities:
            raise NotImplementedError("Switch capability not supported for this device.")
        await self.send_command(
            capability=DeviceCapability.SWITCH,
            command_name=DeviceCommand.SET_SWITCH,
            arguments={"switch": "on"}
        )

        if DeviceCapability.BRIGHTNESS in self.capabilities and "brightness" in kwargs:
            brightness = kwargs["brightness"]
            level = round((brightness / 255) * 100)
            await self.send_command(
                capability=DeviceCapability.BRIGHTNESS,
                command_name=DeviceCommand.SET_LEVEL,
                arguments={"level": level}
            )