"""Tests for normalized lock-state interpretation."""

import pytest

from custom_components.u_tec.lock_state import reported_locked


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ({"st.lock": {"lockState": True}}, True),
        ({"st.lock": {"lockState": False}}, False),
        ({"st.lock": {"lockState": "Locked"}}, True),
        ({"st.lock": {"lockState": "lOcKeD"}}, True),
        ({"st.lock": {"lockState": "Unlocked"}}, False),
        ({"st.lock": {"lockState": "UNLOCKED"}}, False),
        ({}, None),
        ({"st.lock": {}}, None),
        ({"st.lock": {"lockState": "Passage"}}, None),
        ({"st.lock": {"lockState": "Jammed"}}, None),
        ({"st.lock": {"lockState": 1}}, None),
        ({"st.lock": {"lockState": None}}, None),
        ({"st.lock": {"lockState": {"value": "Locked"}}}, None),
        ([{"capability": "st.lock", "name": "lockState", "value": "Locked"}], None),
        (
            {
                "states": [
                    {"capability": "st.lock", "name": "lockState", "value": "Locked"}
                ]
            },
            None,
        ),
        (None, None),
    ],
)
def test_reported_locked_only_accepts_normalized_lock_values(payload, expected):
    assert reported_locked(payload) is expected


@pytest.mark.parametrize(
    ("values", "expected"),
    [
        (["Locked", "Unknown", "Unlocked"], [True, None, False]),
        (["Unlocked", "Unknown", "Locked"], [False, None, True]),
    ],
)
async def test_utec_client_full_replacement_unknown_and_recovery(values, expected):
    """The pinned client replaces normalized state for every raw report."""
    from utec_client.devices.lock import Lock

    device = Lock(
        {
            "id": "lock-1",
            "name": "Test lock",
            "handleType": "utec-lock",
            "category": "lock",
            "deviceInfo": {},
            "attributes": {},
        },
        None,
    )
    for raw_value, observed in zip(values, expected):
        await device.update_state_data(
            {
                "id": "lock-1",
                "states": [
                    {"capability": "st.lock", "name": "lockState", "value": raw_value}
                ],
            }
        )
        normalized = device.get_state_data()
        assert normalized == {"st.lock": {"lockState": raw_value}}
        assert reported_locked(normalized) is observed

    await device.update_state_data({"id": "lock-1", "states": []})
    assert device.get_state_data() == {}
    assert reported_locked(device.get_state_data()) is None

    await device.update_state_data(
        {
            "id": "lock-1",
            "states": [
                {"capability": "st.lock", "name": "lockState", "value": values[-1]}
            ],
        }
    )
    assert reported_locked(device.get_state_data()) is expected[-1]
