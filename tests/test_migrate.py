"""Tests for async_migrate_entry."""

from unittest.mock import AsyncMock, patch

from homeassistant.components.application_credentials import (
    CONF_AUTH_DOMAIN,
    CONF_CLIENT_ID,
    CONF_CLIENT_SECRET,
    CONF_DOMAIN,
    DATA_COMPONENT,
)
from homeassistant.helpers import config_entry_oauth2_flow
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.u_tec import async_migrate_entry
from custom_components.u_tec.const import DOMAIN


async def test_migrate_v1_strips_client_id_and_secret(hass):
    await async_setup_component(hass, "application_credentials", {})
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
    assert entry.minor_version == 2


async def test_migrate_already_current_is_noop(hass):
    await async_setup_component(hass, "application_credentials", {})
    entry = MockConfigEntry(
        domain=DOMAIN,
        entry_id="e2",
        data={"auth_implementation": "u_tec", "token": {"access_token": "a"}},
        version=2,
        minor_version=2,
    )
    entry.add_to_hass(hass)

    assert await async_migrate_entry(hass, entry) is True
    assert entry.version == 2
    assert entry.minor_version == 2


async def test_migrate_rewrites_legacy_auth_implementation_and_rekeys_cred(hass):
    """v2.1 entries pointing at a credential item_id (legacy default) get rekeyed.

    Pre-fix entries created by the original config flow have
    data["auth_implementation"] = "<DOMAIN>.<client_id>" (the credential item_id),
    and the corresponding store record has auth_domain defaulted to the same
    item_id. After this migration the entry must reference the canonical
    "u_tec" auth_domain, and the stored credential's auth_domain must match.
    """
    await async_setup_component(hass, "application_credentials", {})
    storage = hass.data[DATA_COMPONENT]
    # Create a legacy-shaped credential: no explicit auth_domain → defaults to item_id.
    await storage.async_create_item(
        {
            CONF_DOMAIN: DOMAIN,
            CONF_CLIENT_ID: "abc",
            CONF_CLIENT_SECRET: "shh",
        }
    )
    items = list(storage.async_items())
    assert len(items) == 1
    legacy_item_id = items[0]["id"]
    assert items[0].get(CONF_AUTH_DOMAIN) in (None, legacy_item_id)

    entry = MockConfigEntry(
        domain=DOMAIN,
        entry_id="e3",
        data={"auth_implementation": legacy_item_id, "token": {"access_token": "tok"}},
        version=2,
        minor_version=1,
    )
    entry.add_to_hass(hass)

    assert await async_migrate_entry(hass, entry) is True

    assert entry.data["auth_implementation"] == DOMAIN
    assert entry.minor_version == 2

    items = list(storage.async_items())
    u_tec_items = [i for i in items if i[CONF_DOMAIN] == DOMAIN]
    assert len(u_tec_items) == 1
    assert u_tec_items[0][CONF_CLIENT_ID] == "abc"
    assert u_tec_items[0][CONF_CLIENT_SECRET] == "shh"
    assert u_tec_items[0][CONF_AUTH_DOMAIN] == DOMAIN


async def test_migrate_v2_1_with_canonical_auth_implementation_bumps_minor_only(hass):
    """Entry already on canonical auth_implementation, just bump minor_version."""
    await async_setup_component(hass, "application_credentials", {})
    entry = MockConfigEntry(
        domain=DOMAIN,
        entry_id="e4",
        data={"auth_implementation": DOMAIN, "token": {"access_token": "a"}},
        version=2,
        minor_version=1,
    )
    entry.add_to_hass(hass)

    assert await async_migrate_entry(hass, entry) is True
    assert entry.version == 2
    assert entry.minor_version == 2
    assert entry.data["auth_implementation"] == DOMAIN


async def test_migrate_legacy_entry_without_matching_cred_still_bumps(hass):
    """Legacy auth_implementation but no matching credential in the store.

    Defensive case: the user wiped credentials but kept the entry. Migration
    should still bump minor_version and normalize auth_implementation to
    "u_tec" — leaving the rest for the framework's reauth flow.
    """
    await async_setup_component(hass, "application_credentials", {})
    entry = MockConfigEntry(
        domain=DOMAIN,
        entry_id="e5",
        data={"auth_implementation": "u_tec.ghost", "token": {"access_token": "a"}},
        version=2,
        minor_version=1,
    )
    entry.add_to_hass(hass)

    assert await async_migrate_entry(hass, entry) is True
    assert entry.minor_version == 2
    assert entry.data["auth_implementation"] == DOMAIN


async def test_migrate_rolls_back_entry_when_legacy_delete_fails(hass):
    """If the legacy-cred delete fails, the entry must still resolve an impl.

    HA's async_import_client_credential is a no-op on suggested_id collision
    (always the case here — same client_id), so we must delete legacy before
    we can import the canonical cred. If that delete fails after the entry
    has been pointed at the canonical auth_domain, the entry would orphan.

    Mitigation: helper rolls the entry's auth_implementation back to the
    legacy item_id (still in storage), and async_migrate_entry suppresses
    the exception without bumping minor_version. Result: entry loads against
    the still-present legacy cred; migration retries on the next boot.
    """
    await async_setup_component(hass, "application_credentials", {})
    storage = hass.data[DATA_COMPONENT]

    # Legacy cred: auth_domain defaults to item_id (NOT "u_tec").
    await storage.async_create_item(
        {CONF_DOMAIN: DOMAIN, CONF_CLIENT_ID: "abc", CONF_CLIENT_SECRET: "shh"}
    )
    legacy_item_id = next(iter(storage.async_items()))["id"]

    entry = MockConfigEntry(
        domain=DOMAIN,
        entry_id="e6",
        data={"auth_implementation": legacy_item_id, "token": {"access_token": "tok"}},
        version=2,
        minor_version=1,
    )
    entry.add_to_hass(hass)

    with patch.object(
        storage,
        "async_delete_item",
        new=AsyncMock(side_effect=RuntimeError("simulated delete failure")),
    ):
        assert await async_migrate_entry(hass, entry) is True

    # minor_version NOT bumped — migration deferred to next boot.
    assert entry.minor_version == 1
    # Entry rolled back to the legacy item_id so it can still resolve.
    assert entry.data["auth_implementation"] == legacy_item_id
    # Legacy cred still in storage.
    items = list(storage.async_items())
    assert len(items) == 1
    assert items[0][CONF_CLIENT_ID] == "abc"

    # Resolution succeeds via the legacy cred.
    impl = await config_entry_oauth2_flow.async_get_config_entry_implementation(
        hass, entry
    )
    assert impl is not None
