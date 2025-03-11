"""Support for Uhome lights."""

from utec_py.devices.light import Light as UhomeLight
from voluptuous import Any

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_RGB_COLOR,
    ColorMode,
    LightEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import UhomeDataUpdateCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Uhome light based on a config entry."""
    coordinator: UhomeDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]

    async_add_entities(
        UhomeLightEntity(coordinator, device_id)
        for device_id, device in coordinator.devices.items()
        if isinstance(device, UhomeLight)
    )


class UhomeLightEntity(CoordinatorEntity, LightEntity):
    """Representation of a Uhome light."""

    def __init__(self, coordinator: UhomeDataUpdateCoordinator, device_id: str) -> None:
        """Initialize the light."""
        super().__init__(coordinator)
        self._device = coordinator.devices[device_id]
        self._attr_unique_id = f"{DOMAIN}_{device_id}"
        self._attr_name = self._device.name
        self._attr_device_info = self._device.device_info

        # Set supported features
        supported_features = self._device.supported_features
        if "brightness" in supported_features:
            self._attr_supported_color_modes = {ColorMode.BRIGHTNESS}
        if "color" in supported_features:
            self._attr_supported_color_modes = {ColorMode.RGB}
        if "color_temp" in supported_features:
            self._attr_supported_color_modes.add(ColorMode.COLOR_TEMP)

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self.coordinator.last_update_success and self._device.available

    @property
    def is_on(self) -> bool:
        """Return true if light is on."""
        return self._device.is_on

    @property
    def brightness(self) -> int | None:
        """Return the brightness of this light between 0..255."""
        if self._device.brightness is None:
            return None
        return int(self._device.brightness * 2.55)

    @property
    def rgb_color(self) -> tuple[int, int, int] | None:
        """Return the rgb color value [int, int, int]."""
        return self._device.rgb_color

    @property
    def color_temp(self) -> int | None:
        """Return the color temperature in mireds."""
        if self._device.color_temp is None:
            return None
        return int(1000000 / self._device.color_temp)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the light on."""
        brightness = None
        if ATTR_BRIGHTNESS in kwargs:
            brightness = int(kwargs[ATTR_BRIGHTNESS] / 2.55)

        #if ATTR_RGB_COLOR in kwargs:
        #    await self._device.set_rgb_color(*kwargs[ATTR_RGB_COLOR])

        await self._device.turn_on(brightness=brightness)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the light off."""
        await self._device.turn_off()
        await self.coordinator.async_request_refresh()
