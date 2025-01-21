import asyncio
import logging
from itertools import chain
from typing import Optional

from custom_components.tapo.const import DISCOVERY_TIMEOUT
from homeassistant.components import network
from homeassistant.core import HomeAssistant
from homeassistant.helpers import (
    device_registry as dr,
)

async def discovery_utec_devices(hass: HomeAssistant) -> dict[str, DiscoveredDevice]:
    broadcast_addresses = await network.async_get_ipv4_broadcast_addresses(hass)
    discovery_tasks = [
        TapoDiscovery.scan(timeout=DISCOVERY_TIMEOUT, broadcast=str(address))
        for address in broadcast_addresses
    ]
    return {
        dr.format_mac(device.mac): device
        for device in chain(*await asyncio.gather(*discovery_tasks))
    }
