"""Debug Polling Mode buttons for the U-Tec integration."""

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import UhomeDataUpdateCoordinator
from .entity import hub_device_info


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the debug polling buttons."""
    coordinator: UhomeDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id][
        "coordinator"
    ]
    async_add_entities(
        [
            UhomeStartDebugPollingButton(coordinator),
            UhomeStopDebugPollingButton(coordinator),
        ]
    )


class _DebugPollingButton(ButtonEntity):
    """Base for the debug polling buttons."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: UhomeDataUpdateCoordinator, key: str) -> None:
        self.coordinator = coordinator
        self._attr_translation_key = key
        self._attr_unique_id = f"{DOMAIN}_{key}_{coordinator.config_entry.entry_id}"
        self._attr_device_info = hub_device_info(coordinator)


class UhomeStartDebugPollingButton(_DebugPollingButton):
    """Poll every second for two minutes, then return to the normal interval."""

    def __init__(self, coordinator: UhomeDataUpdateCoordinator) -> None:
        super().__init__(coordinator, "start_debug_polling")

    async def async_press(self) -> None:
        self.coordinator.debug.start()


class UhomeStopDebugPollingButton(_DebugPollingButton):
    """End a debug polling session early."""

    def __init__(self, coordinator: UhomeDataUpdateCoordinator) -> None:
        super().__init__(coordinator, "stop_debug_polling")

    async def async_press(self) -> None:
        self.coordinator.debug.stop()
