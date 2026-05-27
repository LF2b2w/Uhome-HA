"""Custom OAuth2 implementations for U-Tec.

U-Tec's token endpoint (``https://oauth.u-tec.com/token``) returns the OAuth
token wrapped in a non-standard envelope::

    {"code": 200, "data": {"access_token": ..., "token_type": "Bearer",
                           "expires_in": 601200, "scope": "openapi", ...}}

Home Assistant's stock OAuth2 implementations expect the RFC-6749 fields at the
top level, so without unwrapping the refresh (and authorization-code) grant
silently produces no usable token and the access token goes stale. These
subclasses unwrap the envelope for both paths: the config-flow
``LocalOAuth2Implementation`` and the runtime application-credentials
``AuthImplementation``.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.application_credentials import AuthImplementation
from homeassistant.helpers import config_entry_oauth2_flow


def _unwrap_utec_token(result: Any) -> dict:
    """Lift U-Tec's nested token payload to the top level.

    Accepts both the wrapped ``{"code","data":{...}}`` shape and an
    already-standard response (passthrough). Raises ``ValueError`` when no
    ``access_token`` is present (an error envelope), so the caller fails loudly
    instead of persisting a token dict with no usable access token.
    """
    if isinstance(result, dict) and "access_token" in result:
        return result
    if isinstance(result, dict):
        data = result.get("data")
        if isinstance(data, dict) and "access_token" in data:
            return data
    raise ValueError(f"U-Tec token response missing access_token: {result!r}")


class _UtecTokenUnwrapMixin:
    """Mixin unwrapping U-Tec's ``{code,data}`` token envelope.

    Overrides ``_token_request`` — used by both the authorization-code and
    refresh-token grants — to normalise the response before HA consumes it.
    """

    async def _token_request(self, data: dict) -> dict:
        return _unwrap_utec_token(await super()._token_request(data))


class UtecLocalOAuth2Implementation(
    _UtecTokenUnwrapMixin, config_entry_oauth2_flow.LocalOAuth2Implementation
):
    """Config-flow LocalOAuth2Implementation with U-Tec envelope unwrapping."""


class UtecAuthImplementation(_UtecTokenUnwrapMixin, AuthImplementation):
    """Runtime application-credentials AuthImplementation with envelope unwrapping."""
