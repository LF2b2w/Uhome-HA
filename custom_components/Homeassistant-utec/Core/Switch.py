from .device_types import (
    BaseDevice,
    DeviceCategory,
    DeviceCapability,
    DeviceCommand,
    PowerState
)

class Switch(BaseDevice):
    """Represents a Switch/Outlet device in the U-Home API."""
    
    @property
    def category(self) -> DeviceCategory:
        """Get the device category."""
        return DeviceCategory.SWITCH if self._discovery_data.get("category") == "switch" else DeviceCategory.PLUG

    @property
    def power_state(self) -> PowerState:
        """Get the current power state."""
        state = self._get_state_value(DeviceCapability.SWITCH, "switch")
        return PowerState(state) if state else PowerState.UNKNOWN

    @property
    def is_on(self) -> bool:
        """Check if the switch is turned on."""
        return self.power_state == PowerState.ON

    async def turn_on(self) -> None:
        """Turn on the switch."""
        command = DeviceCommand(
            capability=DeviceCapability.SWITCH,
            name="on"
        )
        await self.send_command(command)

    async def turn_off(self) -> None:
        """Turn off the switch."""
        command = DeviceCommand(
            capability=DeviceCapability.SWITCH,
            name="off"
        )
        await self.send_command(command)

    async def update(self) -> None:
        """Update device state."""
        await super().update()