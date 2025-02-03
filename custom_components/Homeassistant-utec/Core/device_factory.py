"""Device factory for creating device instances based on discovery data."""
from typing import Dict, Type, Optional
import logging
from .exceptions import DeviceError
from api import UtecAPI
from ..const import (
    ATTR_HANDLE_TYPE,
    ATTR_DEVICE_ID,
    ATTR_NAME,
    ATTR_CATEGORY,
    ATTR_DEVICE_INFO,
    ATTR_ATTRIBUTES,
)
from .device_types import BaseDevice, Light, Lock, Switch

_LOGGER = logging.getLogger(__name__)

class HandleType:
    """Handle types for device capabilities."""
    UTEC_LOCK = "utec-lock"
    UTEC_LOCK_SENSOR = "utec-lock-sensor"
    UTEC_DIMMER = "utec-dimmer"
    UTEC_LIGHT_RGBAW = "utec-light-rgbaw-br"
    UTEC_SWITCH = "utec-switch"

class DeviceCapability:
    """Device capabilities."""
    SWITCH = "Switch"
    LOCK = "Lock"
    BATTERY_LEVEL = "BatteryLevel"
    LOCK_USER = "LockUser"
    DOOR_SENSOR = "DoorSensor"
    BRIGHTNESS = "Brightness"
    COLOR = "Color"
    COLOR_TEMPERATURE = "ColorTemperature"
    SWITCH_LEVEL = "Switch Level"

# Mapping of handle types to their required capabilities
HANDLE_TYPE_CAPABILITIES = {
    HandleType.UTEC_LOCK: {
        DeviceCapability.LOCK,
        DeviceCapability.BATTERY_LEVEL,
        DeviceCapability.LOCK_USER
    },
    HandleType.UTEC_LOCK_SENSOR: {
        DeviceCapability.LOCK,
        DeviceCapability.BATTERY_LEVEL,
        DeviceCapability.DOOR_SENSOR
    },
    HandleType.UTEC_DIMMER: {
        DeviceCapability.SWITCH,
        DeviceCapability.SWITCH_LEVEL
    },
    HandleType.UTEC_LIGHT_RGBAW: {
        DeviceCapability.SWITCH,
        DeviceCapability.BRIGHTNESS,
        DeviceCapability.COLOR,
        DeviceCapability.COLOR_TEMPERATURE
    },
    HandleType.UTEC_SWITCH: {
        DeviceCapability.SWITCH
    }
}

class DeviceFacilitator:
    """Factory for creating device instances based on discovery data."""

    # Map handle types to device classes
    _handle_type_mapping: Dict[str, Type[BaseDevice]] = {
        HandleType.UTEC_LOCK: Lock,
        HandleType.UTEC_LOCK_SENSOR: Lock,
        HandleType.UTEC_DIMMER: Light,
        HandleType.UTEC_LIGHT_RGBAW: Light,
        HandleType.UTEC_SWITCH: Switch
    }

    @classmethod
    def create_device(cls, discovery_data: dict, api: UtecAPI) -> Optional[BaseDevice]:
        """
        Create and return appropriate device instance based on discovery data.

        Args:
            discovery_data: Dictionary containing device discovery information
            api: Instance of UtecApi for device communication

        Returns:
            BaseDevice: Instance of appropriate device class

        Raises:
            DeviceError: If device creation fails or handle type is not supported
        """
        try:
            # Extract required fields
            handle_type = discovery_data.get(ATTR_HANDLE_TYPE)
            device_id = discovery_data.get(ATTR_DEVICE_ID)

            if not handle_type:
                raise DeviceError(
                    f"Missing handle type in discovery data for device: {device_id}"
                )

            # Get the appropriate device class
            device_class = cls._handle_type_mapping.get(handle_type)
            if not device_class:
                _LOGGER.warning(
                    f"Unsupported handle type: {handle_type} for device: {device_id}"
                )
                return None

            # Add capabilities to discovery data
            capabilities = HANDLE_TYPE_CAPABILITIES.get(handle_type, set())
            discovery_data['supported_capabilities'] = capabilities

            # Create device instance
            device = device_class(discovery_data, api)

            # Validate device capabilities
            cls._validate_device_capabilities(device, capabilities)

            return device

        except Exception as err:
            raise DeviceError(
                f"Failed to create device from discovery data: {err}"
            ) from err

    @staticmethod
    def _validate_device_capabilities(device: BaseDevice, required_capabilities: set) -> None:
        """
        Validate that the device has all required capabilities.

        Args:
            device: Device instance to validate
            required_capabilities: Set of required capabilities

        Raises:
            DeviceError: If device is missing required capabilities
        """
        missing_capabilities = required_capabilities - set(device.supported_capabilities)
        if missing_capabilities:
            raise DeviceError(
                f"Device {device.device_id} missing required capabilities: {missing_capabilities}"
            )

    @classmethod
    def register_device_class(
        cls,
        handle_type: str,
        device_class: Type[BaseDevice],
        capabilities: set
    ) -> None:
        """
        Register a new device class for a handle type.

        Args:
            handle_type: Handle type identifier
            device_class: Device class to register
            capabilities: Set of capabilities required for this device type
        """
        cls._handle_type_mapping[handle_type] = device_class
        HANDLE_TYPE_CAPABILITIES[handle_type] = capabilities
        _LOGGER.debug(f"Registered new device class {device_class.__name__} for handle type {handle_type}")

    @classmethod
    def get_supported_handle_types(cls) -> list:
        """
        Get list of supported handle types.

        Returns:
            list: List of supported handle types
        """
        return list(cls._handle_type_mapping.keys())

    @classmethod
    def get_device_capabilities(cls, handle_type: str) -> set:
        """
        Get capabilities for a specific handle type.

        Args:
            handle_type: Handle type to get capabilities for

        Returns:
            set: Set of capabilities for the handle type
        """
        return HANDLE_TYPE_CAPABILITIES.get(handle_type, set())