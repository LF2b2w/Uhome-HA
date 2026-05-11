"""Tests for the credential-replacement flow with deferred store mutation.

Behavior contract: the application_credentials store is NOT touched when the
user submits the credential form. Storage mutation happens only in
async_oauth_create_entry on the OAuth-success path. This means an OAuth
failure leaves any existing credential intact, so a working entry continues
to refresh against valid creds.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Form rendering
# ---------------------------------------------------------------------------


async def test_replace_credentials_form_renders_with_blank_id_when_no_creds(hass):
    """When no credentials exist, the form renders with empty client_id default."""
    from homeassistant.setup import async_setup_component

    from custom_components.u_tec.config_flow import UhomeOAuth2FlowHandler

    await async_setup_component(hass, "application_credentials", {})

    handler = UhomeOAuth2FlowHandler()
    handler.hass = hass
    result = await handler.async_step_replace_credentials()

    assert result["type"] == "form"
    assert result["step_id"] == "replace_credentials"
    schema = result["data_schema"].schema
    client_id_key = next(k for k in schema if str(k) == "client_id")
    assert client_id_key.default() == ""


async def test_replace_credentials_form_prefills_client_id_when_cred_exists(hass):
    """When a credential exists for u_tec, the form's client_id default is prefilled."""
    from homeassistant.components.application_credentials import (
        ClientCredential,
        async_import_client_credential,
    )
    from homeassistant.setup import async_setup_component

    from custom_components.u_tec.config_flow import UhomeOAuth2FlowHandler
    from custom_components.u_tec.const import DOMAIN

    await async_setup_component(hass, "application_credentials", {})
    await async_import_client_credential(
        hass, DOMAIN, ClientCredential("old-id", "old-secret"), "u_tec"
    )

    handler = UhomeOAuth2FlowHandler()
    handler.hass = hass
    result = await handler.async_step_replace_credentials()

    assert result["type"] == "form"
    schema = result["data_schema"].schema
    client_id_key = next(k for k in schema if str(k) == "client_id")
    assert client_id_key.default() == "old-id"
    secret_key = next(k for k in schema if str(k) == "client_secret")
    assert secret_key.default() == ""


# ---------------------------------------------------------------------------
# async_step_user routing — always renders the credential form (no scope step)
# ---------------------------------------------------------------------------


async def test_user_step_renders_replace_form_when_no_creds(hass):
    """Initial setup with no creds: async_step_user goes straight to the form."""
    from homeassistant.setup import async_setup_component

    from custom_components.u_tec.config_flow import UhomeOAuth2FlowHandler

    await async_setup_component(hass, "application_credentials", {})

    handler = UhomeOAuth2FlowHandler()
    handler.hass = hass
    result = await handler.async_step_user()

    assert result["type"] == "form"
    assert result["step_id"] == "replace_credentials"


async def test_user_step_renders_replace_form_when_creds_exist(hass):
    """Initial setup with stale creds (issue #50): async_step_user goes to the form too."""
    from homeassistant.components.application_credentials import (
        ClientCredential,
        async_import_client_credential,
    )
    from homeassistant.setup import async_setup_component

    from custom_components.u_tec.config_flow import UhomeOAuth2FlowHandler
    from custom_components.u_tec.const import DOMAIN

    await async_setup_component(hass, "application_credentials", {})
    await async_import_client_credential(
        hass, DOMAIN, ClientCredential("stale-id", "stale-secret"), "u_tec"
    )

    handler = UhomeOAuth2FlowHandler()
    handler.hass = hass
    result = await handler.async_step_user()

    assert result["type"] == "form"
    assert result["step_id"] == "replace_credentials"


# ---------------------------------------------------------------------------
# Form submit — defers credential storage; store is NOT mutated here
# ---------------------------------------------------------------------------


async def test_replace_credentials_submit_does_not_touch_app_creds_store(hass):
    """Submitting the form does not import or delete anything in the app_creds store."""
    from homeassistant.components.application_credentials import (
        DATA_COMPONENT,
        CONF_CLIENT_ID,
        CONF_DOMAIN,
        ClientCredential,
        async_import_client_credential,
    )
    from homeassistant.setup import async_setup_component

    from custom_components.u_tec.config_flow import UhomeOAuth2FlowHandler
    from custom_components.u_tec.const import DOMAIN

    await async_setup_component(hass, "application_credentials", {})
    await async_import_client_credential(
        hass, DOMAIN, ClientCredential("original-id", "original-secret"), "u_tec"
    )

    handler = UhomeOAuth2FlowHandler()
    handler.hass = hass
    handler.flow_id = "test-flow-id"

    sentinel = {"type": "external", "url": "https://example.com/auth"}
    with patch.object(
        handler, "async_step_auth", new=AsyncMock(return_value=sentinel),
    ):
        result = await handler.async_step_replace_credentials(
            {"client_id": "different-id", "client_secret": "different-secret"}
        )

    assert result is sentinel

    # Storage state must be untouched.
    items = list(hass.data[DATA_COMPONENT].async_items())
    u_tec_items = [i for i in items if i[CONF_DOMAIN] == DOMAIN]
    assert len(u_tec_items) == 1, "Existing cred should not be deleted on form submit"
    assert u_tec_items[0][CONF_CLIENT_ID] == "original-id", (
        "Existing cred should not be replaced on form submit"
    )


async def test_replace_credentials_submit_sets_pending_credential_and_flow_impl(hass):
    """Submitting the form stages the new creds and an in-memory implementation."""
    from homeassistant.helpers import config_entry_oauth2_flow
    from homeassistant.setup import async_setup_component

    from custom_components.u_tec.config_flow import UhomeOAuth2FlowHandler
    from custom_components.u_tec.const import OAUTH2_AUTHORIZE, OAUTH2_TOKEN

    await async_setup_component(hass, "application_credentials", {})

    handler = UhomeOAuth2FlowHandler()
    handler.hass = hass
    handler.flow_id = "test-flow-id"

    sentinel = {"type": "external", "url": "https://example.com/auth"}
    with patch.object(
        handler, "async_step_auth", new=AsyncMock(return_value=sentinel),
    ):
        await handler.async_step_replace_credentials(
            {"client_id": "new-id", "client_secret": "new-secret"}
        )

    assert handler._pending_credential is not None
    assert handler._pending_credential.client_id == "new-id"
    assert handler._pending_credential.client_secret == "new-secret"

    assert isinstance(
        handler.flow_impl, config_entry_oauth2_flow.LocalOAuth2Implementation
    )
    assert handler.flow_impl.client_id == "new-id"
    assert handler.flow_impl.client_secret == "new-secret"
    assert handler.flow_impl.authorize_url == OAUTH2_AUTHORIZE
    assert handler.flow_impl.token_url == OAUTH2_TOKEN


async def test_replace_credentials_validation_blocks_empty_inputs(hass):
    """Empty client_id or client_secret re-renders the form with errors."""
    from homeassistant.setup import async_setup_component

    from custom_components.u_tec.config_flow import UhomeOAuth2FlowHandler

    await async_setup_component(hass, "application_credentials", {})
    handler = UhomeOAuth2FlowHandler()
    handler.hass = hass

    result = await handler.async_step_replace_credentials(
        {"client_id": "  ", "client_secret": "secret"}
    )
    assert result["type"] == "form"
    assert result["step_id"] == "replace_credentials"
    assert result["errors"] == {"base": "empty_credentials"}

    # _pending_credential must NOT be set when validation fails
    assert handler._pending_credential is None

    result2 = await handler.async_step_replace_credentials(
        {"client_id": "id", "client_secret": ""}
    )
    assert result2["type"] == "form"
    assert result2["errors"] == {"base": "empty_credentials"}
    assert handler._pending_credential is None


# ---------------------------------------------------------------------------
# async_step_reconfigure — entry point for working-entry reconfigure
# ---------------------------------------------------------------------------


async def test_reconfigure_step_routes_to_replace_credentials(hass):
    """async_step_reconfigure jumps to async_step_replace_credentials."""
    from custom_components.u_tec.config_flow import UhomeOAuth2FlowHandler

    handler = UhomeOAuth2FlowHandler()
    handler.hass = hass

    sentinel = {"type": "form", "step_id": "replace_credentials"}
    with patch.object(
        handler,
        "async_step_replace_credentials",
        new=AsyncMock(return_value=sentinel),
    ) as mock_replace:
        result = await handler.async_step_reconfigure({"any": "data"})

    mock_replace.assert_awaited_once()
    assert result is sentinel


# ---------------------------------------------------------------------------
# async_oauth_create_entry — commits deferred credential, branches on source
# ---------------------------------------------------------------------------


async def test_async_oauth_create_entry_creates_new_on_user_source_no_pending(hass):
    """No pending creds + source=user: behaves like the original create_entry path."""
    from custom_components.u_tec.config_flow import UhomeOAuth2FlowHandler
    from custom_components.u_tec.const import (
        CONF_HA_DEVICES, CONF_PUSH_DEVICES, CONF_PUSH_ENABLED,
    )

    handler = UhomeOAuth2FlowHandler()
    handler.hass = hass
    handler.context = {"source": "user"}
    flow_impl = MagicMock()
    flow_impl.name = "u_tec"
    handler.flow_impl = flow_impl

    data = {"token": {"access_token": "tok"}, "auth_implementation": "u_tec"}
    result = await handler.async_oauth_create_entry(data)

    assert result["type"] == "create_entry"
    assert result["data"] == data
    options = result["options"]
    assert options[CONF_PUSH_ENABLED] is True
    assert options[CONF_PUSH_DEVICES] == []
    assert options[CONF_HA_DEVICES] == []


async def test_async_oauth_create_entry_commits_pending_credential_on_success(hass):
    """With _pending_credential set, async_oauth_create_entry imports it into the store."""
    from homeassistant.components.application_credentials import (
        DATA_COMPONENT,
        CONF_CLIENT_ID,
        CONF_CLIENT_SECRET,
        CONF_DOMAIN,
        ClientCredential,
    )
    from homeassistant.setup import async_setup_component

    from custom_components.u_tec.config_flow import UhomeOAuth2FlowHandler
    from custom_components.u_tec.const import DOMAIN

    await async_setup_component(hass, "application_credentials", {})

    handler = UhomeOAuth2FlowHandler()
    handler.hass = hass
    handler.context = {"source": "user"}
    handler._pending_credential = ClientCredential("new-id", "new-secret")
    flow_impl = MagicMock()
    flow_impl.name = "u_tec"
    handler.flow_impl = flow_impl

    data = {"token": {"access_token": "tok"}, "auth_implementation": "ignored"}
    result = await handler.async_oauth_create_entry(data)

    assert result["type"] == "create_entry"
    # auth_implementation rewritten to the canonical "u_tec" auth_domain
    assert result["data"]["auth_implementation"] == "u_tec"
    assert result["data"]["token"] == {"access_token": "tok"}

    items = list(hass.data[DATA_COMPONENT].async_items())
    u_tec_items = [i for i in items if i[CONF_DOMAIN] == DOMAIN]
    assert len(u_tec_items) == 1
    assert u_tec_items[0][CONF_CLIENT_ID] == "new-id"
    assert u_tec_items[0][CONF_CLIENT_SECRET] == "new-secret"


async def test_async_oauth_create_entry_replaces_existing_creds_on_commit(hass):
    """Commit deletes pre-existing creds with a different client_id, imports the new one."""
    from homeassistant.components.application_credentials import (
        DATA_COMPONENT,
        CONF_CLIENT_ID,
        CONF_DOMAIN,
        ClientCredential,
        async_import_client_credential,
    )
    from homeassistant.setup import async_setup_component

    from custom_components.u_tec.config_flow import UhomeOAuth2FlowHandler
    from custom_components.u_tec.const import DOMAIN

    await async_setup_component(hass, "application_credentials", {})
    await async_import_client_credential(
        hass, DOMAIN, ClientCredential("old-id", "old-secret"), "u_tec"
    )

    handler = UhomeOAuth2FlowHandler()
    handler.hass = hass
    handler.context = {"source": "user"}
    handler._pending_credential = ClientCredential("new-id", "new-secret")
    flow_impl = MagicMock()
    flow_impl.name = "u_tec"
    handler.flow_impl = flow_impl

    await handler.async_oauth_create_entry(
        {"token": {"access_token": "tok"}, "auth_implementation": "u_tec"}
    )

    items = list(hass.data[DATA_COMPONENT].async_items())
    u_tec_items = [i for i in items if i[CONF_DOMAIN] == DOMAIN]
    assert len(u_tec_items) == 1
    assert u_tec_items[0][CONF_CLIENT_ID] == "new-id"


async def test_async_oauth_create_entry_rotates_secret_when_client_id_matches(hass):
    """Same client_id with new secret: commit deletes the old record then imports new.

    This is the case async_import_item silently no-ops on (duplicate suggested_id);
    the delete-before-import order in _commit_pending_credential ensures the secret
    actually updates.
    """
    from homeassistant.components.application_credentials import (
        DATA_COMPONENT,
        CONF_CLIENT_ID,
        CONF_CLIENT_SECRET,
        CONF_DOMAIN,
        ClientCredential,
        async_import_client_credential,
    )
    from homeassistant.setup import async_setup_component

    from custom_components.u_tec.config_flow import UhomeOAuth2FlowHandler
    from custom_components.u_tec.const import DOMAIN

    await async_setup_component(hass, "application_credentials", {})
    await async_import_client_credential(
        hass, DOMAIN, ClientCredential("same-id", "old-secret"), "u_tec"
    )

    handler = UhomeOAuth2FlowHandler()
    handler.hass = hass
    handler.context = {"source": "user"}
    handler._pending_credential = ClientCredential("same-id", "new-secret")
    flow_impl = MagicMock()
    flow_impl.name = "u_tec"
    handler.flow_impl = flow_impl

    await handler.async_oauth_create_entry(
        {"token": {"access_token": "tok"}, "auth_implementation": "u_tec"}
    )

    items = list(hass.data[DATA_COMPONENT].async_items())
    u_tec_items = [i for i in items if i[CONF_DOMAIN] == DOMAIN]
    assert len(u_tec_items) == 1
    assert u_tec_items[0][CONF_CLIENT_ID] == "same-id"
    assert u_tec_items[0][CONF_CLIENT_SECRET] == "new-secret"


async def test_async_oauth_create_entry_no_pending_does_not_touch_store(hass):
    """Without _pending_credential, the store is untouched and data is unchanged."""
    from homeassistant.components.application_credentials import (
        DATA_COMPONENT,
        CONF_CLIENT_ID,
        CONF_DOMAIN,
        ClientCredential,
        async_import_client_credential,
    )
    from homeassistant.setup import async_setup_component

    from custom_components.u_tec.config_flow import UhomeOAuth2FlowHandler
    from custom_components.u_tec.const import DOMAIN

    await async_setup_component(hass, "application_credentials", {})
    await async_import_client_credential(
        hass, DOMAIN, ClientCredential("orig-id", "orig-secret"), "u_tec"
    )

    handler = UhomeOAuth2FlowHandler()
    handler.hass = hass
    handler.context = {"source": "user"}
    flow_impl = MagicMock()
    flow_impl.name = "u_tec"
    handler.flow_impl = flow_impl

    incoming_data = {"token": {"access_token": "tok"}, "auth_implementation": "u_tec"}
    result = await handler.async_oauth_create_entry(incoming_data)

    # Data passed through unchanged
    assert result["data"] == incoming_data

    items = list(hass.data[DATA_COMPONENT].async_items())
    u_tec_items = [i for i in items if i[CONF_DOMAIN] == DOMAIN]
    assert len(u_tec_items) == 1
    assert u_tec_items[0][CONF_CLIENT_ID] == "orig-id"


async def test_async_oauth_create_entry_updates_existing_on_reconfigure(hass):
    """For source=reconfigure with pending creds, update entry + commit creds."""
    from homeassistant.components.application_credentials import (
        DATA_COMPONENT,
        CONF_CLIENT_ID,
        CONF_DOMAIN,
        ClientCredential,
        async_import_client_credential,
    )
    from homeassistant.setup import async_setup_component
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from custom_components.u_tec.config_flow import UhomeOAuth2FlowHandler
    from custom_components.u_tec.const import (
        CONF_HA_DEVICES, CONF_PUSH_DEVICES, CONF_PUSH_ENABLED, DOMAIN,
    )

    await async_setup_component(hass, "application_credentials", {})
    await async_import_client_credential(
        hass, DOMAIN, ClientCredential("old-id", "old-secret"), "u_tec"
    )

    existing_options = {
        CONF_PUSH_ENABLED: False,
        CONF_PUSH_DEVICES: ["dev-a", "dev-b"],
        CONF_HA_DEVICES: ["dev-a"],
    }
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="u_tec",
        data={"auth_implementation": "u_tec", "token": {"access_token": "old"}},
        options=existing_options,
        version=2,
    )
    entry.add_to_hass(hass)

    handler = UhomeOAuth2FlowHandler()
    handler.hass = hass
    handler.context = {"source": "reconfigure", "entry_id": entry.entry_id}
    handler._pending_credential = ClientCredential("new-id", "new-secret")
    flow_impl = MagicMock()
    flow_impl.name = "u_tec"
    handler.flow_impl = flow_impl

    sentinel = {"type": "abort", "reason": "reconfigure_successful"}
    new_data = {"token": {"access_token": "new"}, "auth_implementation": "ignored"}

    with patch.object(
        handler,
        "async_update_reload_and_abort",
        return_value=sentinel,
    ) as mock_update:
        result = await handler.async_oauth_create_entry(new_data)

    assert result is sentinel
    mock_update.assert_called_once()
    call_args = mock_update.call_args.args
    call_kwargs = mock_update.call_args.kwargs
    assert call_args[0] is entry
    # data passed to update has auth_implementation rewritten
    assert call_kwargs["data"]["auth_implementation"] == "u_tec"
    assert call_kwargs["data"]["token"] == {"access_token": "new"}
    assert call_kwargs["options"] == existing_options

    # And the store is updated
    items = list(hass.data[DATA_COMPONENT].async_items())
    u_tec_items = [i for i in items if i[CONF_DOMAIN] == DOMAIN]
    assert len(u_tec_items) == 1
    assert u_tec_items[0][CONF_CLIENT_ID] == "new-id"


async def test_async_oauth_create_entry_updates_existing_on_reauth(hass):
    """For source=reauth with pending creds, update entry data and commit creds."""
    from homeassistant.components.application_credentials import (
        ClientCredential,
    )
    from homeassistant.setup import async_setup_component
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from custom_components.u_tec.config_flow import UhomeOAuth2FlowHandler
    from custom_components.u_tec.const import (
        CONF_HA_DEVICES, CONF_PUSH_DEVICES, CONF_PUSH_ENABLED, DOMAIN,
    )

    await async_setup_component(hass, "application_credentials", {})

    existing_options = {
        CONF_PUSH_ENABLED: True,
        CONF_PUSH_DEVICES: [],
        CONF_HA_DEVICES: ["dev-x"],
    }
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="u_tec",
        data={"auth_implementation": "u_tec", "token": {"access_token": "old"}},
        options=existing_options,
        version=2,
    )
    entry.add_to_hass(hass)

    handler = UhomeOAuth2FlowHandler()
    handler.hass = hass
    handler.context = {"source": "reauth", "entry_id": entry.entry_id}
    handler._pending_credential = ClientCredential("reauth-id", "reauth-secret")
    flow_impl = MagicMock()
    flow_impl.name = "u_tec"
    handler.flow_impl = flow_impl

    sentinel = {"type": "abort", "reason": "reauth_successful"}
    new_data = {"token": {"access_token": "new"}, "auth_implementation": "ignored"}

    with patch.object(
        handler,
        "async_update_reload_and_abort",
        return_value=sentinel,
    ) as mock_update:
        result = await handler.async_oauth_create_entry(new_data)

    assert result is sentinel
    mock_update.assert_called_once()
    call_args = mock_update.call_args.args
    call_kwargs = mock_update.call_args.kwargs
    assert call_args[0] is entry
    assert call_kwargs["data"]["auth_implementation"] == "u_tec"
    assert call_kwargs["options"] == existing_options
