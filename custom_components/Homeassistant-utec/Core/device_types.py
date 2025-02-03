from enum import Enum
from dataclasses import dataclass
from typing import Optional, Dict, Any, Set, Type, TypedDict

from ..api import UtecAPI
from ..exceptions import DeviceError

class DeviceInfo:
    """Class that represents device information in the U-Home API."""

    def __init__(self, raw_data: dict):
        """Initialize a device info object."""
        self.raw_data = raw_data

    @property
    def manufacturer(self) -> str:
        """Return the manufacturer of the device."""
        return self.raw_data.get("manufacturer", "")

    @property
    def model(self) -> str:
        """Return the model of the device."""
        return self.raw_data.get("model", "")

    @property
    def serial_number(self) -> Optional[str]:
        """Return the serial number of the device."""
        return self.raw_data.get("serialNumber")

class DeviceCategory(str, Enum):
    """Device categories as returned by the API."""
    LOCK = "smartlock"
    PLUG = "smartplug"
    SWITCH = "smartswitch"
    LIGHT = "light"
    UNKNOWN = "unknown"

class HandleType(str, Enum):
    UTEC_LOCK = "utec-lock"
    UTEC_LOCK_SENSOR = "utec-lock-sensor"
    UTEC_DIMMER = "utec-dimmer"
    UTEC_LIGHT_RGBAW = "utec-light-rgbaw-br"
    UTEC_SWITCH = "utec-switch"

class DeviceCapability(str, Enum):
    SWITCH = "Switch"
    LOCK = "Lock"
    BATTERY_LEVEL = "BatteryLevel"
    LOCK_USER = "LockUser"
    DOOR_SENSOR = "DoorSensor"
    BRIGHTNESS = "Brightness"
    COLOR = "Color"
    COLOR_TEMPERATURE = "ColorTemperature"
    SWITCH_LEVEL = "Switch Level"

class DeviceCommand:
    def __init__(self, capability: str, name: str, arguments: Optional[Dict] = None):
        self.capability = capability
        self.name = name
        self.arguments = arguments

class BaseDevice:
    """Base class for all U-Home devices."""

    def __init__(self, discovery_data: dict, api: UtecAPI):
        self._discovery_data = discovery_data
        self._api = api
        self._id = discovery_data["id"]
        self._name = discovery_data["name"]
        self._handle_type = HandleType(discovery_data["handleType"])
        self._supported_capabilities = discovery_data["supportedCapabilities"]
        self._validate_capabilities()

    @property
    def id(self) -> str:
        return self._discovery_data["id"]
    
    @property
    def supported_capabilities(self) -> Set[DeviceCapability]:
        """Get the set of supported capabilities."""
        return self._supported_capabilities
    
    def has_capability(self, capability: DeviceCapability) -> bool:
        """Check if the device supports a specific capability."""
        return capability in self._supported_capabilities
    
    def _validate_capabilities(self) -> None:
        """Validate that the device has the required capabilities."""
        required_capabilities = HANDLE_TYPE_CAPABILITIES[self._handle_type]
        if not required_capabilities.issubset(self._supported_capabilities):
            missing = required_capabilities - self._supported_capabilities
            raise DeviceError(
                f"Device {self._id} missing required capabilities: {missing}"
            )

    async def send_command(self, command: DeviceCommand) -> None:
        """Send command to device."""
        response = await self.api.send_command(
            self.id,
            command.capability,
            command.name,
            command.arguments
        )
        if response and "payload" in response:
            self._state_data = response["payload"]["devices"][0]

    async def update(self) -> None:
        """Update device state."""
        response = await self.api.query_device(self.id)
        if response and "payload" in response:
            self._state_data = response["payload"]["devices"][0]

@dataclass
class DeviceTypeDefinition:
    handle_type: HandleType
    capabilities: Set[DeviceCapability]
    device_class: Type['BaseDevice']  # Forward reference

# Constants for device capabilities by handle type
HANDLE_TYPE_CAPABILITIES: Dict[HandleType, Set[DeviceCapability]] = {
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

class PowerState(str, Enum):
    ON = "on"
    OFF = "off"
    UNKNOWN = "unknown"

@dataclass
class DeviceState:
    capability: str
    name: str
    value: Any

class ColorModel(str, Enum):
    RGB = "RGB"
    HSV = "HSV"

@dataclass
class ColorTemperatureRange:
    min: int
    max: int

@dataclass
class RGBColor:
    r: int
    g: int
    b: int

    def to_dict(self) -> Dict[str, int]:
        return {"r": self.r, "g": self.g, "b": self.b}

    @classmethod
    def from_dict(cls, data: Dict[str, int]) -> 'RGBColor':
        return cls(r=data['r'], g=data['g'], b=data['b'])

class LightAttributes(TypedDict, total=False):
    colorModel: str
    colorTemperatureRange: Dict[str, int]

class LockState(str, Enum):
    LOCKED = "locked"
    UNLOCKED = "unlocked"
    UNKNOWN = "unknown"