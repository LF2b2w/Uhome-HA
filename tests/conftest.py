"""Pytest setup for u_tec tests.

All tests import via the package path: `from custom_components.u_tec... import ...`.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent
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


@pytest.fixture(autouse=True, scope="session")
def _prime_pycares_shutdown_thread():
    """Pre-spawn pycares' ``_run_safe_shutdown_loop`` daemon before per-test
    thread snapshots, so the lingering-thread check never blames a test for it.

    aiohttp's aiodns resolver lazily starts this shared daemon the first time
    any test builds a clientsession (e.g. a real OAuth token refresh). Older
    pytest-homeassistant-custom-component builds have no whitelist for it in
    their cleanup check, so the *first* such test fails teardown — on the
    Python 3.12 CI leg, pip backtracks to homeassistant 2025.1.4 /
    pytest-HA-CC 0.13.205, which predates the whitelist. Starting the thread
    once at session scope (this fixture runs before the function-scoped
    ``verify_cleanup``) puts it in every test's ``threads_before`` baseline, so
    it is never counted as leaked. The loop only blocks on a queue — no socket,
    DNS, or event loop — so it is safe under pytest-socket.
    """
    try:
        import pycares

        pycares._shutdown_manager.start()
    except (ImportError, AttributeError):  # pragma: no cover — pycares internals shifted
        pass
    yield


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
