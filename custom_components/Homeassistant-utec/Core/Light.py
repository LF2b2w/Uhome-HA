from typing import Optional

from .device_types import (
    BaseDevice,
    DeviceCategory,
    DeviceCapability,
    DeviceCommand,
    LightAttributes,
    RGBColor,
    ColorModel,
    ColorTemperatureRange
)
from .exceptions import DeviceError

class Light(BaseDevice):
    """Represents a Light device in the U-Home API."""

    @property
    def category(self) -> DeviceCategory:
        """Get the device category."""
        return DeviceCategory.LIGHT
    @property
    def power_state(self) -> Optional[str]:
        """Get the current power state."""
        return self._get_state_value(DeviceCapability.SWITCH, "switch")

    @property
    def brightness(self) -> Optional[int]:
        """Get the current brightness level (0-100)."""
        return self._get_state_value(DeviceCapability.BRIGHTNESS, "brightness")

    @property
    def color_temperature(self) -> Optional[int]:
        """Get the current color temperature."""
        return self._get_state_value(DeviceCapability.COLOR_TEMP, "temperature")

    @property
    def color(self) -> Optional[RGBColor]:
        """Get the current RGB color."""
        color_dict = self._get_state_value(DeviceCapability.COLOR, "color")
        return RGBColor.from_dict(color_dict) if color_dict else None

    @property
    def color_model(self) -> Optional[ColorModel]:
        """Get the supported color model."""
        model = self._attributes.get("colorModel")
        return ColorModel(model) if model else None

    @property
    def color_temperature_range(self) -> Optional[ColorTemperatureRange]:
        """Get the supported color temperature range."""
        range_dict = self._attributes.get("colorTemperatureRange")
        if range_dict:
            return ColorTemperatureRange(
                min=range_dict["min"],
                max=range_dict["max"]
            )
        return None

    @property
    def is_on(self) -> bool:
        """Check if the light is turned on."""
        return self.power_state == "on"

    async def turn_on(self) -> None:
        """Turn on the light."""
        command = DeviceCommand(
            capability=DeviceCapability.SWITCH,
            name="on"
        )
        await self.send_command(command)

    async def turn_off(self) -> None:
        """Turn off the light."""
        command = DeviceCommand(
            capability=DeviceCapability.SWITCH,
            name="off"
        )
        await self.send_command(command)

    async def set_brightness(self, brightness: int) -> None:
        """Set the brightness level."""
        if not 0 <= brightness <= 100:
            raise ValueError("Brightness must be between 0 and 100")

        command = DeviceCommand(
            capability=DeviceCapability.BRIGHTNESS,
            name="setBrightness",
            arguments={"brightness": brightness}
        )
        await self.send_command(command)

    async def set_color_temperature(self, temperature: int) -> None:
        """Set the color temperature."""
        range_ = self.color_temperature_range
        if range_ and not range_.min <= temperature <= range_.max:
            raise ValueError(
                f"Temperature must be between {range_.min} and {range_.max}"
            )

        command = DeviceCommand(
            capability=DeviceCapability.COLOR_TEMP,
            name="setColorTemperature",
            arguments={"temperature": temperature}
        )
        await self.send_command(command)

    async def set_color(self, color: RGBColor) -> None:
        """Set the RGB color."""
        if self.color_model != ColorModel.RGB:
            raise DeviceError("Device does not support RGB color")

        # Validate RGB values
        for value in (color.r, color.g, color.b):
            if not 0 <= value <= 255:
                raise ValueError("RGB values must be between 0 and 255")

        command = DeviceCommand(
            capability=DeviceCapability.COLOR,
            name="setColor",
            arguments={"color": color.to_dict()}
        )
        await self.send_command(command)

    async def update(self) -> None:
        """Update device state."""
        await super().update()