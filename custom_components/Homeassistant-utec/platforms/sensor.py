from homeassistant.components.sensor import SensorEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from ..const import DOMAIN

class UHomeSensor(CoordinatorEntity, SensorEntity):
    """Representation of a U-Home Sensor."""

    def __init__(self, coordinator, device_id, sensor_type):
        """Initialize the sensor entity."""
        super().__init__(coordinator)
        self.device_id = device_id
        self.sensor_type = sensor_type
        self._device = coordinator.get_device(device_id)

    @property
    def unique_id(self):
        """Return a unique ID for the sensor."""
        return f"{DOMAIN}_sensor_{self.device_id}_{self.sensor_type}"

    @property
    def name(self):
        """Return the name of the sensor."""
        return f"{self._device._name} {self.sensor_type}"

    @property
    def state(self):
        """Return the state of the sensor."""
        if self.sensor_type == "battery":
            return self._device.battery_level
        elif self.sensor_type == "door_state":
            return self._device.door_state
        return None

    @property
    def device_info(self):
        """Return device information for the sensor."""
        return self.coordinator.get_ha_device_info(self._device)

    async def async_update(self):
        """Update the sensor state."""
        await self.coordinator.async_request_refresh()