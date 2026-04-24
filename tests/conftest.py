"""Pytest setup for u_tec tests.

Two test styles coexist:

1. Standalone unit tests (e.g. test_optimistic.py) import the resolver
   module directly via the sys.path insertion below.
2. Integration tests import from `custom_components.u_tec.<module>` and
   rely on fixtures defined here.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent
# Path 1: standalone module import path (for test_optimistic.py).
sys.path.insert(0, str(_REPO_ROOT / "custom_components" / "u_tec"))
# Path 2: package import path (for `from custom_components.u_tec... import ...`).
sys.path.insert(0, str(_REPO_ROOT))

# pytest-homeassistant-custom-component ships its own `custom_components/`
# (with __init__.py) under testing_config/. Python's package resolver picks
# that up first and shadows ours. Extend its __path__ to include our repo's
# custom_components/ so `custom_components.u_tec` resolves.
import custom_components as _custom_components  # noqa: E402

_OUR_CC = str(_REPO_ROOT / "custom_components")
if _OUR_CC not in _custom_components.__path__:
    _custom_components.__path__.insert(0, _OUR_CC)


# Re-export pytest-homeassistant-custom-component fixtures needed by integration
# tests. Importing `enable_custom_integrations` here makes the autouse=True
# fixture globally active — every integration test gets `custom_components/`
# registered automatically.
try:
    from pytest_homeassistant_custom_component.common import MockConfigEntry  # noqa: F401
except ImportError:  # pragma: no cover — only hit if deps missing
    MockConfigEntry = None  # type: ignore


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Automatically enable loading custom components in tests."""
    yield


@pytest.fixture
def mock_uhome_api():
    """Mock utec_py.api.UHomeApi instance."""
    from utec_py.api import UHomeApi

    api = MagicMock(spec=UHomeApi)
    api.send_command = AsyncMock(return_value={"payload": {"devices": []}})
    api.query_device = AsyncMock(return_value={"payload": {"devices": []}})
    api.get_device_state = AsyncMock(return_value={"payload": {"devices": []}})
    api.discover_devices = AsyncMock(return_value={"payload": {"devices": []}})
    api.set_push_status = AsyncMock(return_value={})
    api.validate_auth = AsyncMock(return_value=True)
    return api
