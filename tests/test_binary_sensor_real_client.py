"""Door reports through the real pinned client and Home Assistant entity."""

import pytest
from homeassistant.const import STATE_OFF, STATE_ON
from utec_client.devices.lock import Lock

from custom_components.u_tec.binary_sensor import UhomeDoorSensor
from custom_components.u_tec.coordinator import UhomeDataUpdateCoordinator
from tests.common import make_config_entry


@pytest.mark.parametrize("capability", ["st.DoorSensor", "st.doorSensor"])
@pytest.mark.parametrize(
    "report_kind", ["door", "legacy", "precedence", "cross-alias", "empty-door"]
)
@pytest.mark.parametrize("transport", ["poll", "push"])
async def test_real_client_door_reports_reach_ha(
    hass, mock_uhome_api, capability, report_kind, transport
):
    """Accept both aliases, prefer doorState, and retain legacy fallback."""
    lock = Lock(
        {
            "id": "lock-1",
            "name": "Test lock",
            "handleType": "utec-lock",
            "category": "lock",
            "deviceInfo": {},
            "attributes": {},
        },
        mock_uhome_api,
    )

    def report(value):
        opposite = "Closed" if value == "Open" else "Open"
        other_alias = (
            "st.doorSensor" if capability == "st.DoorSensor" else "st.DoorSensor"
        )
        states = [{"capability": "st.healthCheck", "name": "status", "value": "Online"}]
        if report_kind == "legacy":
            states.append(
                {"capability": capability, "name": "sensorState", "value": value}
            )
        else:
            states.append(
                {
                    "capability": capability,
                    "name": "doorState",
                    "value": "" if report_kind == "empty-door" else value,
                }
            )
            if report_kind in {"precedence", "cross-alias", "empty-door"}:
                states.append(
                    {
                        "capability": (
                            other_alias if report_kind == "cross-alias" else capability
                        ),
                        "name": "sensorState",
                        "value": value if report_kind == "empty-door" else opposite,
                    }
                )
        return {"id": "lock-1", "states": states}

    await lock.update_state_data(report("Closed"))
    assert lock.has_door_sensor
    entry = make_config_entry()
    entry.add_to_hass(hass)
    coordinator = UhomeDataUpdateCoordinator(
        hass,
        mock_uhome_api,
        config_entry=entry,
        scan_interval=10,
        discovery_interval=300,
    )
    coordinator.devices["lock-1"] = lock
    entity = UhomeDoorSensor(coordinator, "lock-1")
    entity.hass = hass
    entity.entity_id = "binary_sensor.test_door"
    await entity.async_added_to_hass()
    try:
        for value, expected in (
            ("Open", STATE_ON),
            ("Closed", STATE_OFF),
            ("Open", STATE_ON),
        ):
            response = {"payload": {"devices": [report(value)]}}
            if transport == "poll":
                mock_uhome_api.get_device_state.return_value = response
                await coordinator.async_refresh()
            else:
                await coordinator.update_push_data(response)
            await hass.async_block_till_done()
            state = hass.states.get(entity.entity_id)
            assert state is not None
            assert state.state == expected
        if transport == "poll":
            assert mock_uhome_api.get_device_state.await_count == 3
    finally:
        await entity.async_remove()
        await hass.async_block_till_done()
