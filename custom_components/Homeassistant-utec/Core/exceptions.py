"""U-Home API exceptions."""

class UtecError(Exception):
    """Base exception for U-Home API."""
    pass

class AuthError(UtecError):
    """Authentication failed."""
    pass

class ApiError(UtecError):
    """API call failed."""
    def __init__(self, status_code, message):
        super().__init__(f"API call failed: {status_code} - {message}")
        self.status_code = status_code
        self.message = message

class ValidationError(UtecError):
    """Validation failed."""
    pass

class DeviceError(Exception):
    """Base exception for device-related errors."""
    pass

class UnsupportedFeatureError(DeviceError):
    """Exception raised when a feature is not supported by the device."""
    pass

class ValidationError(DeviceError):
    """Exception raised when device validation fails."""
    pass