"""Support for U-tec Smart Light."""

from voluptuous import Any

from homeassistant.components.light import LightEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up U-tec light devices."""
    api = hass.data[DOMAIN]
    lights = api.get_lights()
    async_add_entities(UtecLight(light) for light in lights)


class UtecLight(LightEntity):
    """Representation of a U-tec Smart Light."""

    def __init__(self, device) -> None:
        """Initialize the light."""
        self._device = device
        self._attr_name = device.name
        self._attr_unique_id = device.id

    @property
    def is_on(self) -> bool:
        """Return true if the light is on."""
        return self._device.state.get("on", False)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the light on."""
        self._device.turn_on()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the light off."""
        self._device.turn_off()

    async def async_update(self) -> None:
        """Fetch new state data for the light."""
        self._device.update_state()
