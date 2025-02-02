"""Base entity platform for U-tec integration."""
from __future__ import annotations
from typing import Any, Dict, Optional, Type, Callable
import logging

from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo, Entity
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)

from .const import DOMAIN
from discovery.requests import ReqAPI
import devices

_LOGGER = logging.getLogger(__name__)

class UtecDeviceType:
    """Device categories supported by U-tec."""
    LOCK = "SmartLock"
    LIGHT = "Light"
    PLUG = "SmartPlug"
    SWITCH = "SmartSwitch"

class UtecHandleType:
    """Device handle types supported by U-tec."""
    LOCK = "utec-lock"
    LOCK_SENSOR = "utec-lock-sensor"
    LIGHT_RGBW = "utec-bulb-color-rgbw"
    LIGHT_DIMMER = "utec-dimmer"
    SWITCH = "utec-swtich"

class DeviceCapability:
    """Device capabilities supported by U-tec."""
    LOCK = "lockstate"
    BATTERY_LEVEL = "level"
    DOOR_SENSOR = "	sensorstate"
    SWITCH = "Switch"
    SWITCH_LEVEL = "Level"
    #BRIGHTNESS = "Brightness"
    #COLOR = "Color"
    #COLOR_TEMPERATURE = "ColorTemperature"
    HEALTH_CHECK = "HealthCheck"  # Mandatory for all devices


# Map handle types to their capabilities
HANDLE_TYPE_CAPABILITIES = {
    "utec-lock": [
        DeviceCapability.LOCK,
        DeviceCapability.BATTERY_LEVEL,
        DeviceCapability.HEALTH_CHECK,
    ],
    "utec-lock-sensor": [
        DeviceCapability.LOCK,
        DeviceCapability.BATTERY_LEVEL,
        DeviceCapability.DOOR_SENSOR,
        DeviceCapability.HEALTH_CHECK,
    ],
    "utec-dimmer": [
        DeviceCapability.SWITCH,
        DeviceCapability.SWITCH_LEVEL,
        DeviceCapability.HEALTH_CHECK,
    ],
    "utec-switch": [
        DeviceCapability.SWITCH,
        DeviceCapability.HEALTH_CHECK,
    ],
    "utec-light-rgbaw-br": [
        DeviceCapability.SWITCH,
        DeviceCapability.HEALTH_CHECK,
    ],
}

class UtecBaseEntity(CoordinatorEntity, Entity):
    """Base entity class for U-tec devices."""

    def __init__(
        self,
        coordinator: DataUpdateCoordinator,
        config_entry: ConfigEntry,
        device_id: str,
        device_data: Dict[str, Any]
    ) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        self._config_entry = config_entry
        self._device_id = device_id
        self._device_data = device_data
        self._attr_unique_id = device_id
        self._attr_name = device_data.get("name", "")

        # Set up device info
        device_info = device_data.get("deviceInfo", {})
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device_id)},
            name=self._attr_name,
            manufacturer=device_info.get("manufacturer", "U-tec"),
            model=device_info.get("model", ""),
            hw_version=device_info.get("hwVersion", ""),
        )

        # Determine capabilities based on handleType
        self._handle_type = device_data.get("handleType", "")
        self._capabilities = HANDLE_TYPE_CAPABILITIES.get(self._handle_type, [])

    @property
    def capabilities(self) -> list[str]:
        """Return the capabilities of the device."""
        return self._capabilities

    @property
    def handle_type(self) -> str:
        """Return the device handle type."""
        return self._handle_type

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return self.coordinator.last_update_success

    async def async_added_to_hass(self) -> None:
        """Run when entity about to be added to hass."""
        await super().async_added_to_hass()

    @property
    def api_client(self) -> ReqAPI:
        """Return the API client."""
        return self.hass.data[DOMAIN][self._config_entry.entry_id]

class UtecDeviceCoordinator(DataUpdateCoordinator):
    """Class to manage fetching data from U-tec API."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: ReqAPI,
        name: str,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=f"U-tec {name}",
            update_interval=None,  # Define update interval based on needs
        )
        self.client = client
        self._device_id: Optional[str] = None

    async def _async_update_data(self) -> Dict[str, Any]:
        """Fetch data from API."""
        try:
            if self._device_id:
                return await self.client.get_device_status(self._device_id)
            return {}
        except Exception as err:
            _LOGGER.error("Error fetching device status: %s", err)
            raise

# Dictionary mapping device categories to their respective entity classes
HANDLE_TYPE_ENTITY_CLASSES: Dict[str, Type[UtecBaseEntity]] = {
    "utec-lock" : devices.Lock,
    "utec-lock-sensor" : devices.Lock,
    "st.BatteryLevel" : devices.Lock,
    "utec-dimmer" : devices.Light,
    "utec-light-rgbaw-br" : devices.Light,
    "utec-switch" : devices.Plug,
}

def create_entity(
    coordinator: UtecDeviceCoordinator,
    config_entry: ConfigEntry,
    device_data: Dict[str, Any],
) -> Optional[UtecBaseEntity]:
    """Create the appropriate entity based on handle type."""
    handle_type = device_data.get("handleType")

    # Get the entity class from the handle type dictionary
    entity_class = HANDLE_TYPE_ENTITY_CLASSES.get(handle_type)

    if entity_class is None:
        _LOGGER.warning(
            "Unsupported handle type: %s",
            handle_type
        )
        return None

    # Create the entity
    return entity_class(
        coordinator,
        config_entry,
        device_data["id"],
        device_data
    )