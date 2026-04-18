"""Support for Uhome lights."""

import logging
from typing import Any, cast

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_COLOR_TEMP_KELVIN,
    ATTR_RGB_COLOR,
    ColorMode,
    LightEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util.color import value_to_brightness
from utec_py.devices.light import Light as UhomeLight
from utec_py.exceptions import DeviceError

from .const import (
    CONF_OPTIMISTIC_LIGHTS,
    DOMAIN,
    SIGNAL_DEVICE_UPDATE,
    is_optimistic_enabled,
)
from .coordinator import UhomeDataUpdateCoordinator

# use module-level logger
_LOGGER = logging.getLogger(__name__)

# U-Tec reports brightness as 1-100, not 0-100. 
BRIGHTNESS_SCALE = (1, 100)


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

    # Class-level defaults ensure these always exist even if HA restores
    # the entity from cache without calling __init__ again.
    _optimistic_is_on: bool | None = None
    _optimistic_brightness: int | None = None
    _pending_brightness_utec: int | None = None

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
        self._optimistic_is_on: bool | None = None
        self._optimistic_brightness: int | None = None
        # The U-Tec brightness value (1-100) we last sent, used to detect
        # when the device has confirmed the change so we can clear optimistic state.
        self._pending_brightness_utec: int | None = None

        # Set supported color modes based on device capabilities
        self._attr_supported_color_modes = set()
        supported_features = self._device.supported_capabilities

        # "st.brightness" is the actual capability name from the
        # U-Tec API (e.g. dimmer devices report "st.brightness" not "brightness").
        # We check both forms for safety.
        has_brightness = (
            "brightness" in supported_features
            or "st.brightness" in supported_features
            or "st.switchLevel" in supported_features
        )
        has_color = "color" in supported_features or "st.colorControl" in supported_features
        has_color_temp = "color_temp" in supported_features or "st.colorTemperature" in supported_features

        if has_brightness:
            self._attr_supported_color_modes.add(ColorMode.BRIGHTNESS)
        if has_color:
            self._attr_supported_color_modes.add(ColorMode.RGB)
        if has_color_temp:
            self._attr_supported_color_modes.add(ColorMode.COLOR_TEMP)

        # Fall back to on/off if no richer capabilities detected
        if not self._attr_supported_color_modes:
            self._attr_supported_color_modes.add(ColorMode.ONOFF)

        # Set default color mode (richest available wins)
        if ColorMode.RGB in self._attr_supported_color_modes:
            self._attr_color_mode = ColorMode.RGB
        elif ColorMode.COLOR_TEMP in self._attr_supported_color_modes:
            self._attr_color_mode = ColorMode.COLOR_TEMP
        elif ColorMode.BRIGHTNESS in self._attr_supported_color_modes:
            self._attr_color_mode = ColorMode.BRIGHTNESS
        else:
            self._attr_color_mode = ColorMode.ONOFF

    def _is_optimistic(self) -> bool:
        """Return True if optimistic updates apply to this device."""
        return is_optimistic_enabled(
            self.coordinator.config_entry.options,
            CONF_OPTIMISTIC_LIGHTS,
            self._device.device_id,
        )

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self.coordinator.last_update_success and self._device.available

    @property
    def is_on(self) -> bool:
        """Return true if light is on."""
        if self._optimistic_is_on is not None:
            return self._optimistic_is_on
        return self._device.is_on

    @property
    def brightness(self) -> int | None:
        """Return the brightness of this light between 0..255."""
        if self._optimistic_brightness is not None:
            return self._optimistic_brightness
        if self._device.brightness is None:
            return None
        return value_to_brightness(BRIGHTNESS_SCALE, self._device.brightness)

    @property
    def assumed_state(self) -> bool:
        """Return True if the current reported state is optimistic and unconfirmed."""
        return self._is_optimistic() and (
            self._optimistic_is_on is not None
            or self._optimistic_brightness is not None
        )

    def _handle_coordinator_update(self) -> None:
        """Handle updated data from coordinator.

        For both on/off and brightness, only clear optimistic state once the
        device confirms the new value — the first poll after a command often
        still returns the old value.
        """
        if self._optimistic_is_on is not None:
            if self._optimistic_is_on == self._device.is_on:
                self._optimistic_is_on = None
            # else: keep optimistic state until device catches up

        pending = self._pending_brightness_utec
        if pending is not None:
            actual = self._device.brightness
            if actual is not None and actual == pending:
                self._optimistic_brightness = None
                self._pending_brightness_utec = None
            # else: keep optimistic brightness until device catches up
        else:
            self._optimistic_brightness = None

        super()._handle_coordinator_update()

    @property
    def rgb_color(self) -> tuple[int, int, int] | None:
        """Return the rgb color value [int, int, int]."""
        return self._device.rgb_color

    @property
    def color_temp_kelvin(self) -> int | None:
        """Return the color temperature in Kelvin."""
        # HA deprecated the mireds `color_temp` property in favour of
        # `color_temp_kelvin`.
        return self._device.color_temp

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the light on."""
        _LOGGER.debug("Turning on light %s kwargs=%s", self._device.device_id, kwargs)
        try:
            turn_on_args = {}

            if ATTR_BRIGHTNESS in kwargs:
                brightness_255 = kwargs[ATTR_BRIGHTNESS]
                utec_brightness = max(1, int((brightness_255 / 255) * 100))
                turn_on_args["brightness"] = utec_brightness

            if ATTR_RGB_COLOR in kwargs:
                turn_on_args["rgb_color"] = kwargs[ATTR_RGB_COLOR]

            if ATTR_COLOR_TEMP_KELVIN in kwargs:
                turn_on_args["color_temp"] = kwargs[ATTR_COLOR_TEMP_KELVIN]

            await self._device.turn_on(**turn_on_args)

            if self._is_optimistic():
                self._optimistic_is_on = True
                if "brightness" in turn_on_args:
                    self._optimistic_brightness = kwargs[ATTR_BRIGHTNESS]
                    self._pending_brightness_utec = turn_on_args["brightness"]
                self.async_write_ha_state()

        except DeviceError as err:
            _LOGGER.error("Failed to turn on light %s: %s", self._device.device_id, err)
            raise HomeAssistantError(f"Failed to turn on light: {err}") from err

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the light off."""
        _LOGGER.debug("Turning off light %s", self._device.device_id)
        try:
            await self._device.turn_off()
            if self._is_optimistic():
                self._optimistic_is_on = False
                self.async_write_ha_state()
        except DeviceError as err:
            _LOGGER.error(
                "Failed to turn off light %s: %s", self._device.device_id, err
            )
            raise HomeAssistantError(f"Failed to turn off light: {err}") from err

    async def async_added_to_hass(self):
        """Register callbacks."""
        await super().async_added_to_hass()

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
