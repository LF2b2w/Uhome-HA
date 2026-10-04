"""Support for Uhome battery, push, API and Adaptive Aggressive accounting sensors."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, cast

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, EntityCategory, UnitOfTime
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from utec_client.devices.device_const import DeviceCapability
from utec_client.devices.lock import Lock as UhomeLock

from .const import DOMAIN, SIGNAL_DEVICE_UPDATE, SIGNAL_NEW_DEVICE
from .coordinator import UhomeDataUpdateCoordinator
from .entity import hub_device_info
from .stats import KIND_COMMAND, KIND_DISCOVERY, KIND_QUERY

REQUESTS = "requests"
REQUESTS_PER_HOUR = "requests/h"
PUSHES = "pushes"
BURSTS = "bursts"
POLLS = "polls"
CHANGES = "changes"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Uhome battery sensors based on a config entry."""
    coordinator: UhomeDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id][
        "coordinator"
    ]

    entities = _create_battery_entities(coordinator)
    entities.append(UhomeLastPushSensor(coordinator))
    async_add_entities(entities)
    async_add_entities(
        UhomeApiStatSensor(coordinator, description)
        for description in (*API_STAT_SENSORS, *AA_STAT_SENSORS)
    )
    async_add_entities(_create_device_command_entities(coordinator))

    @callback
    def async_add_sensor_entities() -> None:
        entities = _create_battery_entities(coordinator, add_only_new=True)
        async_add_entities(entities)
        async_add_entities(
            _create_device_command_entities(coordinator, add_only_new=True)
        )

    entry.async_on_unload(
        async_dispatcher_connect(hass, SIGNAL_NEW_DEVICE, async_add_sensor_entities)
    )


def _create_battery_entities(coordinator, add_only_new=False):
    """Create battery entities for devices with battery capability."""
    entities = []
    for device_id, device in coordinator.devices.items():
        if hasattr(device, "has_capability") and device.has_capability(
            DeviceCapability.BATTERY_LEVEL
        ):
            # Check if this is a new device
            entity_id = f"{DOMAIN}_battery_{device_id}"
            if add_only_new and entity_id in coordinator.added_sensor_entities:
                continue

            # Add to entities list and mark as added
            entities.append(UhomeBatterySensorEntity(coordinator, device_id))
            coordinator.added_sensor_entities.add(entity_id)

    return entities


class UhomeBatterySensorEntity(CoordinatorEntity, SensorEntity):
    """Representation of a Uhome battery sensor."""

    def __init__(self, coordinator: UhomeDataUpdateCoordinator, device_id: str) -> None:
        """Initialize the battery sensor."""
        super().__init__(coordinator)
        self._device = cast(UhomeLock, coordinator.devices[device_id])
        self._attr_unique_id = f"{DOMAIN}_battery_{device_id}"
        self._attr_name = f"{self._device.name} Battery"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._device.device_id)},
            name=self._device.name,
            manufacturer=self._device.manufacturer,
            model=self._device.model,
            hw_version=self._device.hw_version,
        )
        self._attr_device_class = SensorDeviceClass.BATTERY
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_native_unit_of_measurement = PERCENTAGE

    @property
    def available(self) -> bool:
        """Return True if entity is available.

        Unavailable only when the device is offline or consecutive polls failed.
        """
        return self.coordinator.poll_healthy_enough and self._device.available

    @property
    def native_value(self) -> int | None:
        """Return battery level."""
        return self._device.battery_level

    @property
    def device_class(self) -> SensorDeviceClass | None:
        """Return device class."""
        return self._attr_device_class

    @property
    def state_class(self) -> SensorStateClass | str | None:
        """Return device state class."""
        return self._attr_state_class

    async def async_update(self) -> None:
        """Update device information."""
        await self._device.update()

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
    def _handle_push_update(self, push_data):
        """Update device from push data."""
        self.async_write_ha_state()


class UhomeLastPushSensor(CoordinatorEntity, SensorEntity):
    """Diagnostic sensor: timestamp of the most recent webhook push received.

    Coordinator-level (not per-device): there is no physical device, so it ties
    its device_info to the config entry. A stale value here while devices are still
    changing state (caught by the regular poll) is the signal that U-Tec push delivery
    has died — surfaced by the ha-configs push-health-monitor automation.
    """

    _attr_has_entity_name = False
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: UhomeDataUpdateCoordinator) -> None:
        super().__init__(coordinator)
        entry_id = coordinator.config_entry.entry_id
        self._attr_unique_id = f"{DOMAIN}_last_push_{entry_id}"
        self._attr_name = "Utec Last Push"
        self._attr_device_info = hub_device_info(coordinator)

    @property
    def native_value(self):
        return self.coordinator.last_push_received


@dataclass(frozen=True, kw_only=True)
class UhomeApiStatDescription(SensorEntityDescription):
    """An API accounting sensor on the U-Tec Integration device."""

    value_fn: Callable[[UhomeDataUpdateCoordinator], Any]


# Counters are in memory and restart from zero after a restart or reload;
# TOTAL_INCREASING tells statistics to treat that as a meter reset. Latency
# and last-response change on every request, so they start disabled.
API_STAT_SENSORS: tuple[UhomeApiStatDescription, ...] = (
    UhomeApiStatDescription(
        key="api_requests",
        translation_key="api_requests",
        native_unit_of_measurement=REQUESTS,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda c: c.stats.total_requests,
    ),
    UhomeApiStatDescription(
        key="api_requests_last_hour",
        translation_key="api_requests_last_hour",
        native_unit_of_measurement=REQUESTS_PER_HOUR,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda c: c.stats.requests_last_hour(),
    ),
    UhomeApiStatDescription(
        key="api_requests_per_device_last_hour",
        translation_key="api_requests_per_device_last_hour",
        native_unit_of_measurement=REQUESTS_PER_HOUR,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=lambda c: c.stats.requests_per_device_last_hour(len(c.devices)),
    ),
    UhomeApiStatDescription(
        key="api_queries",
        translation_key="api_queries",
        native_unit_of_measurement=REQUESTS,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda c: c.stats.requests[KIND_QUERY],
    ),
    UhomeApiStatDescription(
        key="api_commands",
        translation_key="api_commands",
        native_unit_of_measurement=REQUESTS,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda c: c.stats.requests[KIND_COMMAND],
    ),
    UhomeApiStatDescription(
        key="api_discoveries",
        translation_key="api_discoveries",
        native_unit_of_measurement=REQUESTS,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda c: c.stats.requests[KIND_DISCOVERY],
    ),
    UhomeApiStatDescription(
        key="api_failures",
        translation_key="api_failures",
        native_unit_of_measurement=REQUESTS,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda c: c.stats.failures,
    ),
    UhomeApiStatDescription(
        key="api_last_latency",
        translation_key="api_last_latency",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.MILLISECONDS,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        entity_registry_enabled_default=False,
        value_fn=lambda c: c.stats.last_latency_ms,
    ),
    UhomeApiStatDescription(
        key="api_last_response",
        translation_key="api_last_response",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_registry_enabled_default=False,
        value_fn=lambda c: c.stats.last_response_at,
    ),
    UhomeApiStatDescription(
        key="pushes_received",
        translation_key="pushes_received",
        native_unit_of_measurement=PUSHES,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda c: c.stats.pushes_received,
    ),
    UhomeApiStatDescription(
        key="pushes_applied",
        translation_key="pushes_applied",
        native_unit_of_measurement=PUSHES,
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_registry_enabled_default=False,
        value_fn=lambda c: c.stats.pushes_applied,
    ),
    UhomeApiStatDescription(
        key="pushes_ignored",
        translation_key="pushes_ignored",
        native_unit_of_measurement=PUSHES,
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_registry_enabled_default=False,
        value_fn=lambda c: c.stats.pushes_ignored,
    ),
)


# Adaptive Aggressive accounting, from coordinator.adaptive.stats. Averages
# cover only bursts where a burst poll caught the change; they are None
# (unknown) until the first catch.
AA_STAT_SENSORS: tuple[UhomeApiStatDescription, ...] = (
    UhomeApiStatDescription(
        key="aa_bursts_started",
        translation_key="aa_bursts_started",
        native_unit_of_measurement=BURSTS,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda c: c.adaptive.stats.bursts_started,
    ),
    UhomeApiStatDescription(
        key="aa_polls",
        translation_key="aa_polls",
        native_unit_of_measurement=POLLS,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda c: c.adaptive.stats.polls,
    ),
    UhomeApiStatDescription(
        key="aa_changes_caught",
        translation_key="aa_changes_caught",
        native_unit_of_measurement=CHANGES,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda c: c.adaptive.stats.changes_caught,
    ),
    UhomeApiStatDescription(
        key="aa_avg_seconds_to_detect",
        translation_key="aa_avg_seconds_to_detect",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=lambda c: c.adaptive.stats.avg_seconds_to_detect,
    ),
    UhomeApiStatDescription(
        key="aa_avg_polls_to_detect",
        translation_key="aa_avg_polls_to_detect",
        native_unit_of_measurement=POLLS,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        entity_registry_enabled_default=False,
        value_fn=lambda c: c.adaptive.stats.avg_polls_to_detect,
    ),
    UhomeApiStatDescription(
        key="aa_ended_by_push",
        translation_key="aa_ended_by_push",
        native_unit_of_measurement=BURSTS,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda c: c.adaptive.stats.ended_by_push,
    ),
    UhomeApiStatDescription(
        key="aa_ended_by_failures",
        translation_key="aa_ended_by_failures",
        native_unit_of_measurement=BURSTS,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda c: c.adaptive.stats.ended_by_failures,
    ),
    UhomeApiStatDescription(
        key="aa_exhausted",
        translation_key="aa_exhausted",
        native_unit_of_measurement=BURSTS,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda c: c.adaptive.stats.exhausted,
    ),
)


class UhomeApiStatSensor(CoordinatorEntity, SensorEntity):
    """Diagnostic: how much this install asks of the shared U-Tec API."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    entity_description: UhomeApiStatDescription

    def __init__(
        self,
        coordinator: UhomeDataUpdateCoordinator,
        description: UhomeApiStatDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        entry_id = coordinator.config_entry.entry_id
        self._attr_unique_id = f"{DOMAIN}_{description.key}_{entry_id}"
        self._attr_device_info = hub_device_info(coordinator)

    @property
    def available(self) -> bool:
        """Always available: it reports on the API, it does not depend on it."""
        return True

    @property
    def native_value(self):
        return self.entity_description.value_fn(self.coordinator)


def _create_device_command_entities(coordinator, add_only_new=False):
    """One commands-sent counter per controllable device."""
    entities = []
    for device_id in coordinator.devices:
        unique_id = f"{DOMAIN}_api_commands_{device_id}"
        if add_only_new and unique_id in coordinator.added_sensor_entities:
            continue
        entities.append(UhomeDeviceCommandsSensor(coordinator, device_id))
        coordinator.added_sensor_entities.add(unique_id)
    return entities


class UhomeDeviceCommandsSensor(CoordinatorEntity, SensorEntity):
    """Diagnostic: commands sent to one device since the last restart."""

    _attr_has_entity_name = True
    _attr_translation_key = "device_api_commands"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_entity_registry_enabled_default = False
    _attr_native_unit_of_measurement = REQUESTS
    _attr_state_class = SensorStateClass.TOTAL_INCREASING

    def __init__(self, coordinator: UhomeDataUpdateCoordinator, device_id: str) -> None:
        super().__init__(coordinator)
        device = coordinator.devices[device_id]
        self._device_id = device_id
        self._attr_unique_id = f"{DOMAIN}_api_commands_{device_id}"
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, device.device_id)})

    @property
    def available(self) -> bool:
        return True

    @property
    def native_value(self) -> int:
        return self.coordinator.stats.device_commands(self._device_id)
