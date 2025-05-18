"""Support for Uhome lights."""

import math
from typing import Any, cast

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_COLOR_TEMP_KELVIN,
    ATTR_RGB_COLOR,
    ColorMode,
    LightEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import _LOGGER, HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util.color import value_to_brightness
from homeassistant.util.percentage import percentage_to_ranged_value
from utec_py.devices.light import Light as UhomeLight
from utec_py.exceptions import DeviceError

from .const import DOMAIN, SIGNAL_DEVICE_UPDATE
from .coordinator import UhomeDataUpdateCoordinator

BRIGHTNESS_SCALE = (0, 100)

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Uhome light based on a config entry."""
    coordinator: UhomeDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id][
        "coordinator"
    ]

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
        self._device = cast(UhomeLight, coordinator.devices[device_id])
        self._attr_unique_id = f"{DOMAIN}_{device_id}"
        self._attr_name = self._device.name
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._device.device_id)},
            name=self._device.name,
            manufacturer=self._device.manufacturer,
            model=self._device.model,
            hw_version=self._device.hw_version,
        )
        self._attr_has_entity_name = True

        # Set supported color modes
        self._attr_supported_color_modes = set()
        supported_features = self._device.supported_capabilities

        if "brightness" in supported_features:
            self._attr_supported_color_modes.add(ColorMode.BRIGHTNESS)
        if "color" in supported_features:
            self._attr_supported_color_modes.add(ColorMode.RGB)
        if "color_temp" in supported_features:
            self._attr_supported_color_modes.add(ColorMode.COLOR_TEMP)

        # Set default color mode
        if ColorMode.RGB in self._attr_supported_color_modes:
            self._attr_color_mode = ColorMode.RGB
        elif ColorMode.COLOR_TEMP in self._attr_supported_color_modes:
            self._attr_color_mode = ColorMode.COLOR_TEMP
        elif ColorMode.BRIGHTNESS in self._attr_supported_color_modes:
            self._attr_color_mode = ColorMode.BRIGHTNESS
        else:
            self._attr_color_mode = ColorMode.ONOFF
            self._attr_supported_color_modes.add(ColorMode.ONOFF)

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
        return value_to_brightness(BRIGHTNESS_SCALE, self._device.brightness)

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
        try:
            turn_on_args = {}

            if ATTR_BRIGHTNESS in kwargs:
                brightness =  math.ceil(percentage_to_ranged_value(BRIGHTNESS_SCALE, kwargs[ATTR_BRIGHTNESS]))
                # Convert from 0-255 to 0-100
                turn_on_args["brightness"] = int(brightness / 2.55)

            if ATTR_RGB_COLOR in kwargs:
                turn_on_args["rgb_color"] = kwargs[ATTR_RGB_COLOR]

            if ATTR_COLOR_TEMP_KELVIN in kwargs:
                turn_on_args["color_temp"] = kwargs[ATTR_COLOR_TEMP_KELVIN]

            await self._device.turn_on(**turn_on_args)
            await self.coordinator.async_request_refresh()

        except DeviceError as err:
            _LOGGER.error("Failed to turn on light %s: %s", self._device.device_id, err)
            raise HomeAssistantError(f"Failed to turn on light: {err}") from err

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the light off."""
        try:
            await self._device.turn_off()
            await self.coordinator.async_request_refresh()
        except DeviceError as err:
            _LOGGER.error(
                "Failed to turn off light %s: %s", self._device.device_id, err
            )
            raise HomeAssistantError(f"Failed to turn off light: {err}") from err

    async def async_added_to_hass(self):
        """Register callbacks."""
        await super().async_added_to_hass()

        # Register update callback for push notifications
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                f"{SIGNAL_DEVICE_UPDATE}_{self._device.device_id}",
                self._handle_push_update,
            )
        )

    @callback
    def _handle_push_update(self, push_data) -> None:
        """Update device from push data."""
        self.async_write_ha_state()
