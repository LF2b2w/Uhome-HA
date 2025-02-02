# custom_components/utec/coordinator.py
"""DataUpdateCoordinator for U-Tec."""
import logging
from datetime import timedelta

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)
from homeassistant.helpers import config_entry_oauth2_flow
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import DOMAIN
from discovery.api import UTecAPIClient, UTecAPIError

_LOGGER = logging.getLogger(__name__)

class UTecDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching U-Tec data."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: config_entry_oauth2_flow.OAuth2Session,
        oauth_session: config_entry_oauth2_flow.OAuth2Session,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=30),
        )
        self.api = UTecAPIClient(
            session=oauth_session,
            api_session=async_get_clientsession(hass),
        )
        self.entry = entry

    async def _async_update_data(self):
        """Fetch data from API endpoint."""
        try:
            # Get all devices and their states
            devices = await self.api.get_devices()
            device_states = {}

            for device in devices:
                try:
                    state = await self.api.get_device_state(device["id"])
                    device_states[device["id"]] = {
                        **device,
                        "state": state
                    }
                except UTecAPIError as err:
                    _LOGGER.error("Error getting state for device %s: %s", device["id"], err)

            return device_states

        except UTecAPIError as err:
            raise UpdateFailed(f"Error communicating with API: {err}")