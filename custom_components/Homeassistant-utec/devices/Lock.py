from homeassistant.components.lock import LockEntity
from entity import UtecBaseEntity
from discovery.requests import DeviceCapability, DeviceCommand

class UtecLock(UtecBaseEntity, LockEntity):
    """Representation of a U-tec lock."""

    async def async_lock(self, **kwargs: Any) -> None:
        """Lock the device."""
        if DeviceCapability.LOCK not in self.capabilities:
            raise NotImplementedError("Lock capability not supported for this device.")
        await self.send_command(
            capability=DeviceCapability.LOCK,
            command_name=DeviceCommand.SET_LOCK,
            arguments={"lock": "locked"}
        )

    async def async_unlock(self, **kwargs: Any) -> None:
        """Unlock the device."""
        if DeviceCapability.LOCK not in self.capabilities:
            raise NotImplementedError("Lock capability not supported for this device.")
        await self.send_command(
            capability=DeviceCapability.LOCK,
            command_name=DeviceCommand.SET_LOCK,
            arguments={"lock": "unlocked"}
        )