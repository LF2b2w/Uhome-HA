from typing import Optional

from .device_types import (
    BaseDevice,
    DeviceCapability,
    DeviceCategory,
    DeviceCommand,
    LockState,
)
from .exceptions import DeviceError

class Lock(BaseDevice):
    """Represents a Lock device in the U-Home API."""

    @property
    def has_door_sensor(self) -> bool:
        """Check if the lock has a door sensor capability."""
        return self.has_capability(DeviceCapability.DOOR_SENSOR)

    @property
    def door_state(self) -> Optional[str]:
        """Get the door state if door sensor is present."""
        if not self.has_door_sensor:
            return None
        return self._get_state_value(DeviceCapability.DOOR_SENSOR, "doorState")

    @property
    def category(self) -> DeviceCategory:
        """Get the device category."""
        return DeviceCategory.LOCK

    @property
    def lock_state(self) -> LockState:
        """Get the current lock state."""
        state = self._get_state_value(DeviceCapability.LOCK, "lockState")
        return LockState(state) if state else LockState.UNKNOWN

    @property
    def battery_level(self) -> Optional[int]:
        """Get the current battery level (0-100)."""
        return self._get_state_value(DeviceCapability.BATTERY, "level")

    @property
    def is_locked(self) -> bool:
        """Check if the lock is in locked state."""
        return self.lock_state == LockState.LOCKED

    async def lock(self) -> None:
        """Lock the device."""
        command = DeviceCommand(
            capability=DeviceCapability.LOCK,
            name="lock"
        )
        await self.send_command(command)

    async def unlock(self) -> None:
        """Unlock the device."""
        command = DeviceCommand(
            capability=DeviceCapability.LOCK,
            name="unlock"
        )
        await self.send_command(command)

    async def update(self) -> None:
        """Update device state."""
        await super().update()