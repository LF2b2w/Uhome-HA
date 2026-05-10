"""Tests for the inline replace-credentials flow (issue #50 + reconfigure)."""


async def test_replace_credentials_form_renders_with_blank_id_when_no_creds(hass):
    """When no credentials exist, the form renders with empty client_id default."""
    from homeassistant.setup import async_setup_component

    from custom_components.u_tec.config_flow import UhomeOAuth2FlowHandler

    # Set up application_credentials but DON'T register any cred for u_tec
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


async def test_user_step_routes_to_replace_when_creds_exist(hass):
    """When creds are pre-registered, async_step_user routes to replace_credentials."""
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


async def test_user_step_shows_normal_form_when_no_creds(hass):
    """When no creds exist, async_step_user renders the existing user form."""
    from homeassistant.setup import async_setup_component

    from custom_components.u_tec.config_flow import UhomeOAuth2FlowHandler

    await async_setup_component(hass, "application_credentials", {})

    handler = UhomeOAuth2FlowHandler()
    handler.hass = hass
    result = await handler.async_step_user()

    assert result["type"] == "form"
    assert result["step_id"] == "user"


async def test_replace_credentials_imports_new_and_deletes_old(hass):
    """Submitting the form imports the new cred and removes the old one(s)."""
    from unittest.mock import AsyncMock, patch

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
    handler.flow_id = "test-flow-id"

    sentinel = {"type": "external", "url": "https://example.com/auth"}
    with patch.object(
        handler, "async_step_pick_implementation",
        new=AsyncMock(return_value=sentinel),
    ):
        result = await handler.async_step_replace_credentials(
            {"client_id": "new-id", "client_secret": "new-secret"}
        )

    assert result is sentinel

    items = list(hass.data[DATA_COMPONENT].async_items())
    u_tec_items = [i for i in items if i[CONF_DOMAIN] == DOMAIN]
    assert len(u_tec_items) == 1
    assert u_tec_items[0][CONF_CLIENT_ID] == "new-id"


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

    result2 = await handler.async_step_replace_credentials(
        {"client_id": "id", "client_secret": ""}
    )
    assert result2["type"] == "form"
    assert result2["errors"] == {"base": "empty_credentials"}


async def test_replace_credentials_handles_import_failure(hass):
    """If async_import_client_credential raises, form re-renders with error."""
    from unittest.mock import patch

    from homeassistant.setup import async_setup_component

    from custom_components.u_tec.config_flow import UhomeOAuth2FlowHandler

    await async_setup_component(hass, "application_credentials", {})
    handler = UhomeOAuth2FlowHandler()
    handler.hass = hass

    with patch(
        "custom_components.u_tec.config_flow.async_import_client_credential",
        side_effect=ValueError("boom"),
    ):
        result = await handler.async_step_replace_credentials(
            {"client_id": "new-id", "client_secret": "new-secret"}
        )

    assert result["type"] == "form"
    assert result["step_id"] == "replace_credentials"
    assert result["errors"] == {"base": "credential_import_failed"}


async def test_reconfigure_step_routes_to_replace_credentials(hass):
    """async_step_reconfigure jumps to async_step_replace_credentials."""
    from unittest.mock import AsyncMock, patch

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


async def test_async_oauth_create_entry_creates_new_on_user_source(hass):
    """For source=user (initial setup), behavior is unchanged: create_entry result."""
    from unittest.mock import MagicMock

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


async def test_async_oauth_create_entry_updates_existing_on_reconfigure(hass):
    """For source=reconfigure, update the entry and preserve its options."""
    from unittest.mock import MagicMock, patch

    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from custom_components.u_tec.config_flow import UhomeOAuth2FlowHandler
    from custom_components.u_tec.const import (
        CONF_HA_DEVICES, CONF_PUSH_DEVICES, CONF_PUSH_ENABLED, DOMAIN,
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
    flow_impl = MagicMock()
    flow_impl.name = "u_tec"
    handler.flow_impl = flow_impl

    sentinel = {"type": "abort", "reason": "reconfigure_successful"}
    new_data = {"token": {"access_token": "new"}, "auth_implementation": "u_tec"}

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
    assert call_kwargs["data"] == new_data
    assert call_kwargs["options"] == existing_options


async def test_async_oauth_create_entry_updates_existing_on_reauth(hass):
    """For source=reauth, update the entry data and preserve its options."""
    from unittest.mock import MagicMock, patch

    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from custom_components.u_tec.config_flow import UhomeOAuth2FlowHandler
    from custom_components.u_tec.const import (
        CONF_HA_DEVICES, CONF_PUSH_DEVICES, CONF_PUSH_ENABLED, DOMAIN,
    )

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
    flow_impl = MagicMock()
    flow_impl.name = "u_tec"
    handler.flow_impl = flow_impl

    sentinel = {"type": "abort", "reason": "reauth_successful"}
    new_data = {"token": {"access_token": "new"}, "auth_implementation": "u_tec"}

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
    assert call_kwargs["data"] == new_data
    assert call_kwargs["options"] == existing_options
