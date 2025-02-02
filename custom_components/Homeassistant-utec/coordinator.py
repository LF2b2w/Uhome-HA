"""Data update coordinator."""
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

class YourIntegrationDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching data from API."""
    # Handles periodic updates and caching
    # Reduces API calls by coordinating updates across entities