"""Data coordinator for Uhome integration."""

from datetime import timedelta
import logging

from custom_components.u_tec.const import (
    DEFAULT_DISCOVERY_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    SIGNAL_DEVICE_UPDATE,
    SIGNAL_NEW_DEVICE,
)

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from utec_py.api import UHomeApi
from utec_py.devices.device import BaseDevice
from utec_py.devices.light import Light
from utec_py.devices.lock import Lock
from utec_py.devices.switch import Switch
from utec_py.exceptions import ApiError, AuthenticationError

_LOGGER = logging.getLogger(__name__)


class UhomeDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching Uhome data."""

    def __init__(
        self,
        hass: HomeAssistant,
        api: UHomeApi,
        scan_interval: int = DEFAULT_SCAN_INTERVAL,
        discovery_interval: int = DEFAULT_DISCOVERY_INTERVAL,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name="Uhome devices",
            update_interval=timedelta(seconds=scan_interval),
        )
        self.api = api
        self.devices: dict[str, BaseDevice] = {}
        self.added_sensor_entities = set()
        self.push_devices = []
        self.blacklisted_devices = []
        self._discovery_interval = timedelta(seconds=discovery_interval)
        self._cancel_discovery: callable | None = None
        _LOGGER.info(
            "Uhome data coordinator initialized (poll=%ds, discovery=%ds)",
            scan_interval,
            discovery_interval,
        )

    async def async_start_periodic_discovery(self) -> None:
        """Start periodic device discovery separate from state polling."""
        if self._cancel_discovery:
            self._cancel_discovery()
        self._cancel_discovery = async_track_time_interval(
            self.hass,
            self._async_scheduled_discovery,
            self._discovery_interval,
        )
        _LOGGER.debug("Scheduled periodic device discovery every %s", self._discovery_interval)

    def async_stop_periodic_discovery(self) -> None:
        """Cancel the periodic discovery timer."""
        if self._cancel_discovery:
            self._cancel_discovery()
            self._cancel_discovery = None

    async def async_discover_devices(self) -> None:
        """Discover devices and register any new ones. Does not update state."""
        _LOGGER.debug("Discovering Uhome devices")
        try:
            discovery_data = await self.api.discover_devices()
        except (ApiError, AuthenticationError) as err:
            _LOGGER.error("Device discovery failed: %s", err)
            return

        if not discovery_data or "payload" not in discovery_data:
            _LOGGER.error("Invalid discovery data received: %s", discovery_data)
            return

        devices_data = discovery_data.get("payload", {}).get("devices", [])
        _LOGGER.debug("Found %s devices in discovery data", len(devices_data))

        new_device_ids: list[str] = []
        for device_data in devices_data:
            device_id = device_data.get("id")
            if not device_id or device_id in self.devices:
                continue

            handle_type = device_data.get("handleType", "").lower()
            # "dimmer" check must come before "switch" since "utec-dimmer"
            # contains neither "light" nor "switch".
            if "lock" in handle_type:
                _LOGGER.info("Adding new lock device: %s", device_id)
                device = Lock(device_data, self.api)
            elif "dimmer" in handle_type or "light" in handle_type or "bulb" in handle_type:
                _LOGGER.info("Adding new light/dimmer device: %s [%s]", device_id, handle_type)
                device = Light(device_data, self.api)
            elif "switch" in handle_type:
                _LOGGER.info("Adding new switch device: %s", device_id)
                device = Switch(device_data, self.api)
            else:
                _LOGGER.debug(
                    "Skipping device %s with unsupported handle type: %s",
                    device_id,
                    handle_type,
                )
                continue

            self.devices[device_id] = device
            new_device_ids.append(device_id)

        if new_device_ids:
            # Fetch initial state for all new devices in a single bulk call.
            try:
                response = await self.api.get_device_state(new_device_ids, None)
                if response and "payload" in response:
                    for device_data in response["payload"].get("devices", []):
                        device_id = device_data.get("id")
                        if device_id and device_id in self.devices:
                            await self.devices[device_id].update_state_data(device_data)
            except (ApiError, AuthenticationError) as err:
                _LOGGER.error("Error fetching initial state for new devices: %s", err)
            for device_id in new_device_ids:
                async_dispatcher_send(self.hass, SIGNAL_NEW_DEVICE)

    async def _async_scheduled_discovery(self, _now) -> None:
        """Callback from the periodic discovery timer."""
        await self.async_discover_devices()

    async def _async_update_data(self) -> dict[str, dict]:
        """Fetch state for all known devices in a single bulk API call."""
        if not self.devices:
            return {}

        _LOGGER.debug("Polling state for %d Uhome devices (bulk)", len(self.devices))
        try:
            device_ids = list(self.devices.keys())
            response = await self.api.get_device_state(device_ids, None)
        except AuthenticationError as err:
            raise ConfigEntryAuthFailed(f"Credentials expired: {err}") from err
        except ApiError as err:
            raise UpdateFailed(f"Error communicating with API: {err}") from err

        if response and "payload" in response:
            for device_data in response["payload"].get("devices", []):
                device_id = device_data.get("id")
                if device_id and device_id in self.devices:
                    await self.devices[device_id].update_state_data(device_data)

        return {
            device_id: device.get_state_data()
            for device_id, device in self.devices.items()
        }

    async def update_push_data(self, push_data):
        """Process push update from webhook."""

        _LOGGER.debug("Processing push update: %s", push_data)

        # The webhook payload from U-Tec's server can arrive in two
        # shapes:
        #   (a) {"payload": {"devices": [...]}}  — the expected nested shape
        #   (b) A flat list of device-state dicts  — seen in production (Issue #30,
        #       the "'list' object has no attribute 'get'" crash)
        # We normalise both into a list of device dicts before processing.

        try:
            devices_data = []

            if isinstance(push_data, list):
                # Shape (b): the payload itself is the list
                _LOGGER.debug("Push data is a flat list — normalising")
                devices_data = push_data
            elif isinstance(push_data, dict):
                payload = push_data.get("payload", {})
                if isinstance(payload, list):
                    # Occasionally payload is itself the list
                    devices_data = payload
                elif isinstance(payload, dict):
                    raw = payload.get("devices", [])
                    if isinstance(raw, list):
                        devices_data = raw
                    else:
                        _LOGGER.warning("Unexpected 'devices' value in push payload: %s", raw)
                else:
                    _LOGGER.warning("Unexpected push payload type %s: %s", type(payload), push_data)
            else:
                _LOGGER.warning("Unrecognised push data type %s: %s", type(push_data), push_data)

            if not devices_data:
                _LOGGER.debug("No device data found in push update")
                return

            for device_data in devices_data:
                if not isinstance(device_data, dict):
                    _LOGGER.warning("Skipping non-dict device entry in push update: %s", device_data)
                    continue

                device_id = device_data.get("id")

                if not device_id:
                    _LOGGER.warning("Device ID missing in push update")
                    continue

                # Check if this device should receive push updates
                if self.push_devices and device_id not in self.push_devices:
                    _LOGGER.debug(
                        "Skipping push update for device %s (not in selected devices)",
                        device_id,
                    )
                    continue

                if device_id in self.devices:
                    device = self.devices[device_id]
                    await device.update_state_data(device_data)

                    _LOGGER.debug(
                        "Updated device %s with push data: %s",
                        device_id,
                        device_data,
                    )

                    async_dispatcher_send(
                        self.hass,
                        f"{SIGNAL_DEVICE_UPDATE}_{device_id}",
                        device.get_state_data(),
                    )
                else:
                    _LOGGER.debug(
                        "Received update for unknown device: %s", device_id
                    )

            # Trigger data update for all entities
            self.async_set_updated_data(self.data)

        except (ValueError, TypeError, AttributeError) as err:
            _LOGGER.error("Error processing push update: %s", err)
