"""Tests for async_migrate_entry."""

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.u_tec import async_migrate_entry
from custom_components.u_tec.const import DOMAIN


async def test_migrate_v1_strips_client_id_and_secret(hass):
    entry = MockConfigEntry(
        domain=DOMAIN,
        entry_id="e1",
        data={
            "auth_implementation": "u_tec",
            "client_id": "legacy-id",
            "client_secret": "legacy-secret",
            "token": {"access_token": "a"},
        },
        version=1,
        minor_version=1,
    )
    entry.add_to_hass(hass)

    assert await async_migrate_entry(hass, entry) is True
    assert "client_id" not in entry.data
    assert "client_secret" not in entry.data
    assert entry.data["token"] == {"access_token": "a"}
    assert entry.version == 2


async def test_migrate_already_v2_is_noop(hass):
    entry = MockConfigEntry(
        domain=DOMAIN,
        entry_id="e2",
        data={"auth_implementation": "u_tec", "token": {"access_token": "a"}},
        version=2,
        minor_version=1,
    )
    entry.add_to_hass(hass)

    assert await async_migrate_entry(hass, entry) is True
    assert entry.version == 2
