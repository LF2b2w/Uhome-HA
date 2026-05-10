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
