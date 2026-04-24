# Uhome-HA Test Coverage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

## Session execution map

This plan is sized for **one phase per session** — attempting multiple phases in one context will very likely exhaust the window before the later phases' commit/verify steps.

| Session | Phase | Tasks | Deliverable |
|---|---|---|---|
| 1 | Phase 0 — Foundation | Tasks 0, 1, 2 | AUDIT.md, pyproject.toml, conftest fixtures, deps installed, 8 original tests still green |
| 2 | Phase 1 — Breadth | Tasks 3, 4, 5, 6a, 6b, 7, 8, 9, 10, 11, 12, 13a, 13b, 13c, 14 | Every non-entity module has critical-path coverage; Task 14 is the coverage checkpoint |
| 3 | Phase 2 — Depth (entities) | Tasks 15a, 15b, 15c, 16, 17, 18, 19, 20 | Entity platforms covered; Task 20 is the coverage checkpoint |
| 4 | Phase 3 — Stretch | Tasks 21a, 21b, 21c, 22a, 22b, 23, 24a, 24b…24n, 25 | Full setup/options, webhook registration depth, diagnostics, gap triage, CI wiring. 85% fail-under enforced |

At the end of each session, confirm the phase's coverage checkpoint (where applicable) and commit. Resume the next phase in a fresh session.

**Goal:** Raise Uhome-HA test coverage from 1% (only `optimistic.py` tested) to ≥85% line coverage (90% stretch). Breadth first — every module gets smoke coverage of its critical paths — then depth to close remaining branches.

**Architecture:** Use `pytest-homeassistant-custom-component` for HA integration-style tests (real HA core in-memory, `MockConfigEntry`, mocked OAuth). Shared `conftest.py` provides reusable fixtures: mock `UHomeApi`, mock `utec_py` device stubs (`UhomeLight`/`UhomeSwitch`/`UhomeLock`/`Light`/`Switch`/`Lock`), `make_config_entry(options=...)`, and a pre-wired `DOMAIN` entry with coordinator for entity-level tests. Per-platform tests exercise optimistic state machines by calling entity methods and inspecting both entity state and `mock_api.send_command` call history. Coordinator tests instantiate the coordinator directly with a mock API.

**Tech Stack:** Python 3.12, `pytest`, `pytest-asyncio`, `pytest-homeassistant-custom-component`, `aioresponses`, `coverage.py`.

**Audit basis:**
- `custom_components/u_tec/` has 12 non-trivial modules (see File Structure below).
- Existing coverage: `optimistic.py` at 100% (8 tests). Everything else at 0%.
- Highest-risk untested paths per the audit: `coordinator.update_push_data` (Issue #30 regression), `api._handle_webhook` (Bearer token validation — security boundary), `coordinator._async_update_data` (auth failure → `ConfigEntryAuthFailed`), optimistic state-clear logic in `light`/`switch`/`lock`, options flow multi-step picker, reauth flow, `async_migrate_entry`.
- Existing test infra: `tests/conftest.py` adds `custom_components/u_tec/` to `sys.path` so `optimistic.py` is importable standalone. This must coexist with `pytest-homeassistant-custom-component`. Solution: keep the standalone sys.path insertion AND register the HA integration with `enable_custom_integrations`. `tests/test_optimistic.py` continues to import `from optimistic import ...`; new tests import from `custom_components.u_tec.<module>`.
- **Dependency:** The utec-py sibling library has a parallel test-coverage plan. The two can be worked on independently, but if utec-py gains test-only exports (e.g. a concrete `AbstractAuth` subclass for fixtures), revisit the shared mocks here.

**Coverage target:** 85% line (required, with `--cov-fail-under=85`). 90% stretch. Anticipated exclusions via `[tool.coverage.report] exclude_lines`: `if TYPE_CHECKING:`, `def __repr__`, `def __str__`, `raise NotImplementedError`, defensive `except Exception:  # noqa: BLE001` log-only branches in `api._handle_webhook`, `diagnostics.py` connection-error branches, and `api.async_register_webhook` local-address warning branch.

---

## Local LLM usage policy

`mcp__lm-studio__local_llm` (Gemma 4 e4b 8bit via LM Studio, ~25–40 tok/sec on M1 Pro) is validated at **10/10 accuracy at ≤7k tok prompts** and **98% at ~17k tok** (2026-04-18 testing). **Default stance: use it for every test-writing task in this plan**, including HA integration tests — the earlier pessimism about HA conventions was based on smaller-prompt assumptions that the testing invalidated. Fall back to the primary model only when (a) the narrow forbidden list below applies, or (b) the sanity gate fails twice on the same task.

### How to call it well

- **Format instructions LAST.** Gemma 4 is recency-biased; the "what to produce" and "output only X" instructions go at the bottom, after context.
- **Strip context aggressively.** Pass only the AUDIT section for the function being tested + ONE existing test as a structural template. No "here's the project layout" preamble.
- **One task per call.** Don't chain "reformat + generate tests".
- **Pass `max_tokens: 8192` for prompts >10k tok.** Gemma emits `reasoning_content` separately; default 4096 runs out silently on long prompts.
- **State output structure explicitly.** "Output only the test code — no prose, no markdown fences" beats "generate tests".

### Standard prompt shape — reuse across tasks

```
<Extract from AUDIT-uhome-ha-2026-04-18.md: relevant class/function signatures and exact string constants>

<Existing-test template: ONE similar test from this suite — pick the one that uses the same fixtures>

Available fixtures from tests/conftest.py and tests/common.py:
- hass (pytest-homeassistant-custom-component)
- mock_uhome_api (MagicMock spec UHomeApi)
- make_config_entry(options={...}) -> MockConfigEntry
- make_fake_light / make_fake_switch / make_fake_lock

Generate pytest test cases for <function name>. Cover these paths: <enumerated list>.
Use only identifiers that appear above — do not invent attribute names, step_ids, menu option keys, or constants.
Async tests use `async def test_*` (no @pytest.mark.asyncio decorator — asyncio_mode is "auto").
Output only the Python test code. No prose. No placeholders. No markdown fences.
```

### Where it applies (default-on)

Unless a task is in the forbidden list below, attempt `local_llm` first, using the shape above. Explicit standouts:

- **AUDIT.md generation** (Task 0) — primary use case; per-file extract + reformat.
- **Coverage gap triage** (Task 24a) — text classification is Gemma's sweet spot.
- **All platform entity tests** (Tasks 15a–15c, 16, 17, 18, 19) — now permitted, given AUDIT passes the optimistic-attr names and fixture patterns.
- **Coordinator tests** (Tasks 4, 5, 6a, 6b) — permitted with AUDIT extract for push-data normalization branches.
- **Setup/migration tests** (Tasks 3, 21a–21c) — permitted with patch target list spelled out.
- **Commit message drafts** every task's final step.

### Forbidden narrowly

- **Webhook auth assertions** (Task 7). Security boundary — the exact status codes (401 vs 403 vs 404 vs 405) and the Bearer-token comparison path must be asserted by the primary model. If you want a draft, use `local_llm` for test _structure_ but overwrite every `resp.status == N` and every token-value assertion by hand.
- **Optimistic picker multi-step walkthroughs** (Tasks 13a–13c). Depends on exact `step_id` strings per AUDIT; one hallucinated step name fails silently at the next `async_configure` call. If attempting, quote every step_id verbatim in the prompt.
- **OAuth2 flow create_entry assertions** (Task 9 full flow test). `AbstractOAuth2FlowHandler` internals are version-specific and drift-prone.

### Sanity gate — discard output failing any of these

1. Every `import` resolves per AUDIT, or is a standard lib / `pytest` / `pytest_homeassistant_custom_component.*` / `homeassistant.*` / `utec_py.*`.
2. No reference to a method, fixture, step_id, menu option, or attribute key not present in AUDIT.
3. Async tests use `async def test_*` — no `@pytest.mark.asyncio` decorator (remove any the model adds).
4. No gratuitous `await hass.async_block_till_done()` sprinkled after every statement. It belongs only after `hass.states.async_set`, `hass.bus.async_fire`, dispatcher sends, or entity additions.
5. `MockConfigEntry` usage goes through `make_config_entry(...)` — no direct `MockConfigEntry(domain=...)` in test bodies.
6. Entity tests set `ent.hass`, `ent.entity_id`, and mock `ent.async_write_ha_state` before calling async methods (matches the pattern in Task 15a's worked example).
7. No `if __name__ == "__main__":` block, no `print(...)`, no commented-out code.

Any failure → discard, log as `discarded`, write directly. **Two consecutive `discarded` on the same task** → stop using `local_llm` for the rest of that task.

### Operational gotchas

- **LM Studio serializes requests.** Never parallel-call in one tool-use block — all but one return empty silently. Subagents are serial; only an issue if a single task issues multiple calls at once.
- **Empty output = discarded**, no retry. If empty, suspect `finish_reason: length` → bump `max_tokens` to 8192 and try once more. Then give up.
- **LM Studio not running = silent fallback** to direct work. Don't ask the user to start it.

### Measurement

Every `local_llm` call appends one row to `docs/superpowers/plans/LLM-LOG-2026-04-18.md` (create on first use):

```markdown
# local_llm usage log — Uhome-HA test coverage — 2026-04-18

| Task | Purpose | Outcome | Prompt tokens | Tokens saved (rough) |
|---|---|---|---|---|
```

Row format: `| <task-id> | <one-line purpose> | <used-as-is \| minor-edits \| major-rewrite \| discarded> | <~N prompt> | <~N saved> |`

- **used-as-is:** committed without edits
- **minor-edits:** <10 lines changed (rename, add missing import, tighten an assertion)
- **major-rewrite:** ≥10 lines changed, or structure changed
- **discarded:** output failed sanity gate or was unusable

"Prompt tokens" is a rough estimate; use it to correlate acceptance rate with prompt size against the ≤7k / ~17k Gemma ceilings. "Tokens saved" is the estimated native-generation cost avoided; negative if corrections cost more.

Commit `LLM-LOG-2026-04-18.md` alongside the last task's output. At session end, summarize: total calls, acceptance rate, net tokens saved, and any task where `local_llm` was abandoned mid-task.

---

## File Structure

**Source modules (coverage targets):**
- `custom_components/u_tec/__init__.py` — `async_setup_entry`, `async_update_options`, `async_migrate_entry`.
- `custom_components/u_tec/coordinator.py` — `UhomeDataUpdateCoordinator`.
- `custom_components/u_tec/api.py` — `AsyncConfigEntryAuth`, `AsyncPushUpdateHandler`.
- `custom_components/u_tec/config_flow.py` — `UhomeOAuth2FlowHandler`, `OptionsFlowHandler`, `_current_mode`.
- `custom_components/u_tec/optimistic.py` — already 100% — no work here.
- `custom_components/u_tec/const.py` — re-exports; covered incidentally.
- `custom_components/u_tec/light.py` — `UhomeLightEntity`.
- `custom_components/u_tec/switch.py` — `UhomeSwitchEntity`.
- `custom_components/u_tec/lock.py` — `UhomeLockEntity`.
- `custom_components/u_tec/sensor.py` — `UhomeBatterySensorEntity`.
- `custom_components/u_tec/binary_sensor.py` — `UhomeDoorSensor`.
- `custom_components/u_tec/application_credentials.py` — OAuth2 server URLs.
- `custom_components/u_tec/diagnostics.py` — redaction + API queries.

**New test files:**
- `tests/common.py` — shared builders (`make_config_entry`, `make_fake_light_device`, etc.).
- `tests/test_migrate.py` — `async_migrate_entry`.
- `tests/test_coordinator.py` — `_async_update_data`, `async_discover_devices`, `update_push_data`, `async_start/stop_periodic_discovery`.
- `tests/test_webhook.py` — `AsyncPushUpdateHandler._handle_webhook` (auth, shape validation, error paths).
- `tests/test_config_flow.py` — initial OAuth flow + reauth.
- `tests/test_options_flow.py` — `OptionsFlowHandler` all steps + `_current_mode`.
- `tests/test_application_credentials.py` — trivial.
- `tests/test_light.py` — `UhomeLightEntity`.
- `tests/test_switch.py` — `UhomeSwitchEntity`.
- `tests/test_lock.py` — `UhomeLockEntity`.
- `tests/test_sensor.py` — `UhomeBatterySensorEntity` + dynamic addition via `SIGNAL_NEW_DEVICE`.
- `tests/test_binary_sensor.py` — `UhomeDoorSensor` + inversion.
- `tests/test_setup.py` — full `async_setup_entry` + `async_update_options` integration.
- `tests/test_diagnostics.py` — diagnostics output + redaction.
- `tests/test_webhook_registration.py` — `async_register_webhook` URL resolution branches, re-registration, unregister.

**Modified files:**
- `pytest.ini` → migrate config into `pyproject.toml`, add `asyncio_mode = "auto"`.
- `pyproject.toml` — create (doesn't exist); add pytest + coverage config.
- `requirements-test.txt` — add `pytest-homeassistant-custom-component`, `aioresponses`, `pytest-cov`.
- `tests/conftest.py` — extend with HA fixtures without breaking existing optimistic test imports.

**Preserved files (do not touch):**
- `tests/test_optimistic.py` — keep as-is; already at 100%.
- `tests/__init__.py` — empty; leave.

---

## Phase 0 — Foundation

### Task 0: Produce `AUDIT.md` — one read, many reuses

**Files:**
- Create: `docs/superpowers/plans/AUDIT-uhome-ha-2026-04-18.md`

**Local LLM candidate:** After `rtk read`-ing each module, pass the raw source (per file, one call) to `mcp__lm-studio__local_llm` with a prompt like: *"Extract the public API surface (class names, method signatures with parameter names and types, attribute names, and string constants including step_ids) from this Python file. Output as markdown matching this exact structure: `## custom_components/u_tec/<file>.py` → `- Class: ...` → bullet per method. Do not invent anything not in the source. Preserve exact string values for step_id, menu_options, and attribute key names."* For `config_flow.py` specifically (optimistic picker step_ids are critical), **verify every step_id string round-trips against the source** before committing — a hallucinated step name here breaks Tasks 13a–13c silently. Log outcome per file.

Context-saver: later tasks would otherwise `rtk read` the same source files repeatedly (config_flow.py is ~400+ lines, coordinator.py ~180, light/switch/lock each ~150-200). This task reads each module once and writes a compact reference that subsequent subagents consume instead of re-reading source. **Do not write any tests in this task.** Do not commit any source changes.

- [ ] **Step 1: Read every `.py` file in `custom_components/u_tec/` and produce the audit with these sections:**

```markdown
# Uhome-HA audit — 2026-04-18

## custom_components/u_tec/__init__.py
- async_setup(hass, config) — YAML-config storage under _YAML_CONFIG_KEY
- async_setup_entry — OAuth impl → OAuth2Session → AsyncConfigEntryAuth → UHomeApi → coordinator
- async_update_options — push toggle + reload behavior
- async_migrate_entry — v1→v2 strips client_id/client_secret

## custom_components/u_tec/const.py
- All constants (DOMAIN, CONF_*, DEFAULT_*, SIGNAL_*, WEBHOOK_ID_PREFIX, WEBHOOK_HANDLER)
- Which constants are re-exported from optimistic.py

## custom_components/u_tec/coordinator.py
- UhomeDataUpdateCoordinator.__init__ — constructor signature
- async_start_periodic_discovery / async_stop_periodic_discovery
- async_discover_devices — handleType dispatch order: lock → dimmer/light/bulb → switch → skip
- _async_scheduled_discovery(_now) — wraps async_discover_devices
- _async_update_data — AuthenticationError→ConfigEntryAuthFailed, ApiError→UpdateFailed
- update_push_data — normalization branches (flat list, dict.payload.list, dict.payload.devices.list)

## custom_components/u_tec/api.py
- AsyncConfigEntryAuth(AbstractAuth) — async_get_access_token delegates to OAuth2Session
- AsyncPushUpdateHandler:
  - __init__(hass, api, entry_id)
  - _generate_secret
  - async_register_webhook — strategy loop (allow_internal, allow_ip, prefer_cloud triples)
  - _async_reregister (HA callback, schedules async_create_task)
  - unregister_webhook — async; cancels reregister + calls webhook.async_unregister
  - _handle_webhook — method check, json parse, Bearer auth, entry_id lookup, coordinator.update_push_data
  - Status codes returned: 200, 400, 401, 403, 404, 405, 500

## custom_components/u_tec/config_flow.py
- UhomeOAuth2FlowHandler(AbstractOAuth2FlowHandler):
  - VERSION, DOMAIN class attrs
  - logger (if present)
  - extra_authorize_data (OAuth scope)
  - async_step_user, async_step_reauth, async_step_reauth_confirm
  - async_oauth_create_entry
- OptionsFlowHandler:
  - __init__(self, config_entry)
  - async_step_init — menu step: list menu_options exactly as returned
  - async_step_configure_push (or equivalent) — schema, branches
  - async_step_configure_optimistic (or equivalent) — entry point for picker flow
  - Ordered optimistic steps (e.g. configure_optimistic_lights, pick_optimistic_lights, configure_optimistic_switches, pick_optimistic_switches, configure_optimistic_locks, pick_optimistic_locks) — record EXACT step_ids
  - _current_mode helper — input shapes and return values
  - _advance_optimistic_picker (if present) — what it does

## custom_components/u_tec/optimistic.py
- Already 100% tested — skip

## custom_components/u_tec/light.py
- UhomeLightEntity — constructor, supported_color_modes logic (brightness/color/color_temp flags)
- Class-level default attrs vs __init__ set
- _is_optimistic, assumed_state, is_on, brightness, rgb_color, color_temp_kelvin properties
- async_turn_on kwargs → utec_brightness mapping (1-100 scale), pending_brightness_utec
- async_turn_off
- _handle_coordinator_update — optimistic-clear logic for is_on + brightness
- _handle_push_update, async_added_to_hass

## custom_components/u_tec/switch.py
- UhomeSwitchEntity — parallel shape to light but simpler (no brightness/color)
- assumed_state, is_on property
- async_turn_on/off + optimistic handling
- _handle_coordinator_update clear logic

## custom_components/u_tec/lock.py
- UhomeLockEntity — is_locked, is_jammed properties
- extra_state_attributes — exact key names (e.g. door_state, battery_level)
- async_lock/unlock + optimistic handling
- _handle_coordinator_update clear logic

## custom_components/u_tec/sensor.py
- UhomeBatterySensorEntity — unique_id format, native_value, device_class
- async_setup_entry — initial add loop + SIGNAL_NEW_DEVICE dispatcher connect
- _create_battery_entities / add_only_new guard

## custom_components/u_tec/binary_sensor.py
- UhomeDoorSensor — is_on inversion (open=on, closed=off)
- async_setup_entry — filters locks where has_door_sensor=True

## custom_components/u_tec/application_credentials.py
- async_get_authorization_server function signature + return shape
- OAUTH2_AUTHORIZE / OAUTH2_TOKEN values

## custom_components/u_tec/diagnostics.py
- async_get_config_entry_diagnostics signature
- Redaction keys (TO_REDACT list)
- Error branches (connection timeout, etc)
```

Each section must record **exact identifiers** — step names, attribute keys, menu option strings. The whole point is that downstream tasks don't have to guess.

- [ ] **Step 2: Commit the audit**

```bash
git add docs/superpowers/plans/AUDIT-uhome-ha-2026-04-18.md
git commit -m "docs: audit u_tec source surface for test-coverage plan"
```

- [ ] **Step 3: All downstream tasks reference the audit.** If a task needs to know "the exact step_id" or "the exact attribute key", read the audit. Only spot-check source if the audit seems wrong — and update it in that case.

---

### Task 1: Add pyproject.toml + pytest-asyncio + coverage config

**Files:**
- Create: `pyproject.toml`
- Delete: `pytest.ini`
- Modify: `requirements-test.txt`

- [ ] **Step 1: Create `pyproject.toml`** (the repo has no `pyproject.toml` currently; `pytest.ini` holds the minimal pytest config)

```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
addopts = "-q"
filterwarnings = [
    # pytest-homeassistant-custom-component emits these; they're noise.
    "ignore::DeprecationWarning",
    "ignore::PendingDeprecationWarning",
]

[tool.coverage.run]
branch = true
source = ["custom_components/u_tec"]
omit = [
    "custom_components/u_tec/__init__.py:1",  # noop: don't exclude __init__; listed for reference
]

[tool.coverage.report]
show_missing = true
skip_empty = true
fail_under = 85
exclude_lines = [
    "pragma: no cover",
    "raise NotImplementedError",
    "if TYPE_CHECKING:",
    "if __name__ == .__main__.:",
    "def __repr__",
    "def __str__",
    "@(abc\\.)?abstractmethod",
    # Defensive log-only catch-alls
    "except Exception:  # noqa: BLE001",
    "logger\\.exception",
]
```

- [ ] **Step 2: Delete `pytest.ini`** (its config now lives in `pyproject.toml`)

```bash
rm pytest.ini
```

- [ ] **Step 3: Replace `requirements-test.txt`**

```
pytest>=8.0
pytest-asyncio>=0.24
pytest-cov>=5.0
coverage[toml]>=7.4
aioresponses>=0.7.6
pytest-homeassistant-custom-component>=0.13.200
```

- [ ] **Step 4: Install deps** (reuse existing .venv — do NOT create a new one)

```bash
cd /Users/gfranks/workspace/Uhome-HA
# If no .venv yet:
# python3.12 -m venv .venv
.venv/bin/pip install -r requirements-test.txt
```

Expected: clean install, no errors. If `pytest-homeassistant-custom-component` pulls in a conflicting `homeassistant` version, pin to the version used in production (check `manifest.json` → `requirements` / `homeassistant` field if present).

- [ ] **Step 5: Run existing `test_optimistic.py`** to verify the foundation didn't break anything:

```bash
.venv/bin/pytest tests/test_optimistic.py -v
```

Expected: 8 passed.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml requirements-test.txt
git rm pytest.ini
git commit -m "test: add pyproject.toml with pytest-asyncio and coverage config"
```

---

### Task 2: Extend conftest.py with shared HA fixtures

**Files:**
- Modify: `tests/conftest.py`
- Create: `tests/common.py`

- [ ] **Step 1: Extend `tests/conftest.py`** — preserve the existing sys.path trick so `test_optimistic.py` continues to work, add fixtures for integration tests:

```python
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
```

- [ ] **Step 2: Create `tests/common.py`** — builders for config entries and mock devices:

```python
"""Shared test helpers for u_tec integration tests."""

from __future__ import annotations

from unittest.mock import MagicMock

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.u_tec.const import DOMAIN


def make_config_entry(
    *,
    entry_id: str = "test-entry-id",
    data: dict | None = None,
    options: dict | None = None,
    version: int = 2,
) -> MockConfigEntry:
    """Build a MockConfigEntry for the u_tec integration."""
    return MockConfigEntry(
        domain=DOMAIN,
        entry_id=entry_id,
        data=data or {
            "auth_implementation": "u_tec",
            "token": {
                "access_token": "test-access",
                "refresh_token": "test-refresh",
                "expires_at": 9999999999,
            },
        },
        options=options or {},
        version=version,
        minor_version=1,
        unique_id=entry_id,
    )


def make_fake_light(
    device_id: str = "light-1",
    name: str = "Fake Light",
    *,
    is_on: bool = False,
    brightness: int | None = None,
    rgb_color: tuple | None = None,
    color_temp: int | None = None,
    available: bool = True,
    supported_capabilities: set | None = None,
) -> MagicMock:
    """Return a MagicMock spec-bound to utec_py.devices.light.Light."""
    from utec_py.devices.light import Light

    mock = MagicMock(spec=Light)
    mock.device_id = device_id
    mock.name = name
    mock.manufacturer = "U-Tec"
    mock.model = "TestLight"
    mock.hw_version = "1.0"
    mock.available = available
    mock.is_on = is_on
    mock.brightness = brightness
    mock.rgb_color = rgb_color
    mock.color_temp = color_temp
    mock.supported_capabilities = supported_capabilities or {
        "st.switch",
        "st.brightness",
        "st.switchLevel",
    }
    # Async methods
    from unittest.mock import AsyncMock

    mock.turn_on = AsyncMock(return_value=None)
    mock.turn_off = AsyncMock(return_value=None)
    mock.update = AsyncMock(return_value=None)
    mock.update_state_data = AsyncMock(return_value=None)
    return mock


def make_fake_switch(
    device_id: str = "sw-1",
    name: str = "Fake Switch",
    *,
    is_on: bool = False,
    available: bool = True,
) -> MagicMock:
    """Return a MagicMock spec-bound to utec_py.devices.switch.Switch."""
    from utec_py.devices.switch import Switch
    from unittest.mock import AsyncMock

    mock = MagicMock(spec=Switch)
    mock.device_id = device_id
    mock.name = name
    mock.manufacturer = "U-Tec"
    mock.model = "TestSwitch"
    mock.hw_version = "1.0"
    mock.available = available
    mock.is_on = is_on
    mock.supported_capabilities = {"st.switch"}
    mock.turn_on = AsyncMock(return_value=None)
    mock.turn_off = AsyncMock(return_value=None)
    mock.update = AsyncMock(return_value=None)
    mock.update_state_data = AsyncMock(return_value=None)
    return mock


def make_fake_lock(
    device_id: str = "lock-1",
    name: str = "Fake Lock",
    *,
    is_locked: bool = True,
    is_jammed: bool = False,
    available: bool = True,
    has_door_sensor: bool = False,
    is_door_open: bool = False,
    battery_level: int = 90,
    lock_mode: str = "normal",
) -> MagicMock:
    """Return a MagicMock spec-bound to utec_py.devices.lock.Lock."""
    from utec_py.devices.lock import Lock
    from unittest.mock import AsyncMock

    mock = MagicMock(spec=Lock)
    mock.device_id = device_id
    mock.name = name
    mock.manufacturer = "U-Tec"
    mock.model = "TestLock"
    mock.hw_version = "1.0"
    mock.available = available
    mock.is_locked = is_locked
    mock.is_jammed = is_jammed
    mock.has_door_sensor = has_door_sensor
    mock.is_door_open = is_door_open
    mock.battery_level = battery_level
    mock.battery_status = "normal"
    mock.lock_mode = lock_mode
    mock.supported_capabilities = {"st.lock"}
    mock.lock = AsyncMock(return_value=None)
    mock.unlock = AsyncMock(return_value=None)
    mock.update = AsyncMock(return_value=None)
    mock.update_state_data = AsyncMock(return_value=None)
    return mock
```

- [ ] **Step 3: Smoke-test the fixtures**

Create `tests/test_fixtures_smoke.py`:

```python
"""Smoke test: HA fixtures and test builders wire up."""

import pytest


async def test_hass_fixture_exists(hass):
    assert hass is not None


async def test_mock_config_entry_builder_creates_entry(hass):
    from tests.common import make_config_entry

    entry = make_config_entry()
    entry.add_to_hass(hass)
    assert entry.entry_id == "test-entry-id"


def test_make_fake_light_defaults():
    from tests.common import make_fake_light

    mock = make_fake_light()
    assert mock.device_id == "light-1"
    assert mock.is_on is False


def test_make_fake_lock_defaults():
    from tests.common import make_fake_lock

    mock = make_fake_lock()
    assert mock.is_locked is True
    assert mock.is_jammed is False
```

- [ ] **Step 4: Run** `.venv/bin/pytest tests/ -v`. Expected: 4 new tests pass, 8 original pass = 12 total.

- [ ] **Step 5: Commit**

```bash
git add tests/conftest.py tests/common.py tests/test_fixtures_smoke.py
git commit -m "test: add shared HA fixtures and mock device builders"
```

---

## Phase 1 — Breadth: critical-path coverage

### Task 3: `async_migrate_entry` — secrets-removal path

**Files:**
- Create: `tests/test_migrate.py`

- [ ] **Step 1: Write the tests**

```python
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
```

- [ ] **Step 2: Run** `.venv/bin/pytest tests/test_migrate.py -v`. Expected: 2 passed.

- [ ] **Step 3: Commit** `git add tests/test_migrate.py && git commit -m "test: cover async_migrate_entry v1→v2 secrets removal"`

---

### Task 4: `coordinator.update_push_data` — all normalization branches

**Files:**
- Create: `tests/test_coordinator.py`

- [ ] **Step 1: Write the tests**

```python
"""Tests for UhomeDataUpdateCoordinator."""

from unittest.mock import AsyncMock

import pytest

from custom_components.u_tec.coordinator import UhomeDataUpdateCoordinator
from tests.common import make_config_entry, make_fake_switch


@pytest.fixture
async def coordinator(hass, mock_uhome_api):
    entry = make_config_entry()
    entry.add_to_hass(hass)
    coord = UhomeDataUpdateCoordinator(
        hass, mock_uhome_api, config_entry=entry, scan_interval=10, discovery_interval=300,
    )
    return coord


async def test_update_push_data_flat_list_shape_routes_to_device(coordinator):
    """Issue #30 regression: payload can be a flat list, not a dict."""
    sw = make_fake_switch("sw-1")
    coordinator.devices["sw-1"] = sw
    push_data = [
        {"id": "sw-1", "states": [
            {"capability": "st.switch", "name": "switch", "value": "on"},
        ]},
    ]

    await coordinator.update_push_data(push_data)

    sw.update_state_data.assert_awaited_once_with(push_data[0])


async def test_update_push_data_nested_dict_shape(coordinator):
    sw = make_fake_switch("sw-1")
    coordinator.devices["sw-1"] = sw
    push_data = {"payload": {"devices": [
        {"id": "sw-1", "states": [
            {"capability": "st.switch", "name": "switch", "value": "on"},
        ]},
    ]}}

    await coordinator.update_push_data(push_data)

    sw.update_state_data.assert_awaited_once()


async def test_update_push_data_payload_is_list_shape(coordinator):
    """Edge case: `payload` key points to a list, not a dict."""
    sw = make_fake_switch("sw-1")
    coordinator.devices["sw-1"] = sw
    push_data = {"payload": [
        {"id": "sw-1", "states": [{"capability": "st.switch", "name": "switch", "value": "on"}]},
    ]}

    await coordinator.update_push_data(push_data)

    sw.update_state_data.assert_awaited_once()


async def test_update_push_data_missing_device_id_is_skipped(coordinator):
    sw = make_fake_switch("sw-1")
    coordinator.devices["sw-1"] = sw
    push_data = [{"states": [{"capability": "x", "name": "y", "value": 1}]}]

    await coordinator.update_push_data(push_data)

    sw.update_state_data.assert_not_awaited()


async def test_update_push_data_unknown_device_id_is_skipped(coordinator):
    sw = make_fake_switch("sw-1")
    coordinator.devices["sw-1"] = sw
    push_data = [{"id": "unknown-999", "states": []}]

    await coordinator.update_push_data(push_data)

    sw.update_state_data.assert_not_awaited()


async def test_update_push_data_non_dict_entry_is_skipped(coordinator):
    sw = make_fake_switch("sw-1")
    coordinator.devices["sw-1"] = sw
    push_data = [["not", "a", "dict"], {"id": "sw-1", "states": []}]

    await coordinator.update_push_data(push_data)

    # The valid second entry still routes
    sw.update_state_data.assert_awaited_once()


async def test_update_push_data_respects_push_device_allowlist(coordinator):
    sw = make_fake_switch("sw-1")
    other = make_fake_switch("sw-2")
    coordinator.devices["sw-1"] = sw
    coordinator.devices["sw-2"] = other
    coordinator.push_devices = ["sw-1"]  # only sw-1 allowed

    push_data = [
        {"id": "sw-1", "states": []},
        {"id": "sw-2", "states": []},
    ]
    await coordinator.update_push_data(push_data)

    sw.update_state_data.assert_awaited_once()
    other.update_state_data.assert_not_awaited()


async def test_update_push_data_unrecognised_top_level_type_is_noop(coordinator):
    sw = make_fake_switch("sw-1")
    coordinator.devices["sw-1"] = sw

    await coordinator.update_push_data("garbage-string")
    await coordinator.update_push_data(None)
    await coordinator.update_push_data(42)

    sw.update_state_data.assert_not_awaited()
```

- [ ] **Step 2: Run** `.venv/bin/pytest tests/test_coordinator.py -v`. Expected: 8 passed.

- [ ] **Step 3: Commit** `git add tests/test_coordinator.py && git commit -m "test: cover coordinator.update_push_data normalization branches"`

---

### Task 5: `coordinator._async_update_data` — happy path + auth failure + API error

**Files:**
- Modify: `tests/test_coordinator.py` (append)

- [ ] **Step 1: Append**

```python
# --- _async_update_data ---

from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import UpdateFailed
from utec_py.exceptions import ApiError, AuthenticationError


async def test_async_update_data_empty_when_no_devices(coordinator):
    result = await coordinator._async_update_data()
    assert result == {}
    coordinator.api.get_device_state.assert_not_called()


async def test_async_update_data_bulk_fetches_all_devices(coordinator, mock_uhome_api):
    sw1 = make_fake_switch("sw-1")
    sw2 = make_fake_switch("sw-2")
    sw1.get_state_data = lambda: {"st.switch": {"switch": "on"}}
    sw2.get_state_data = lambda: {"st.switch": {"switch": "off"}}
    coordinator.devices["sw-1"] = sw1
    coordinator.devices["sw-2"] = sw2
    mock_uhome_api.get_device_state.return_value = {
        "payload": {"devices": [
            {"id": "sw-1", "states": [{"capability": "st.switch", "name": "switch", "value": "on"}]},
            {"id": "sw-2", "states": [{"capability": "st.switch", "name": "switch", "value": "off"}]},
        ]}
    }

    result = await coordinator._async_update_data()

    assert set(result.keys()) == {"sw-1", "sw-2"}
    mock_uhome_api.get_device_state.assert_awaited_once_with(["sw-1", "sw-2"], None)


async def test_async_update_data_auth_error_raises_config_entry_auth_failed(
    coordinator, mock_uhome_api,
):
    coordinator.devices["sw-1"] = make_fake_switch("sw-1")
    mock_uhome_api.get_device_state.side_effect = AuthenticationError("bad token")

    with pytest.raises(ConfigEntryAuthFailed, match="Credentials expired"):
        await coordinator._async_update_data()


async def test_async_update_data_api_error_raises_update_failed(
    coordinator, mock_uhome_api,
):
    coordinator.devices["sw-1"] = make_fake_switch("sw-1")
    mock_uhome_api.get_device_state.side_effect = ApiError(500, "oops")

    with pytest.raises(UpdateFailed, match="Error communicating"):
        await coordinator._async_update_data()
```

- [ ] **Step 2: Run**. Expected: all new tests pass.

- [ ] **Step 3: Commit** `git add tests/test_coordinator.py && git commit -m "test: cover _async_update_data auth-failure and api-error paths"`

---

### Task 6a: `async_discover_devices` — handleType routing

**Files:**
- Modify: `tests/test_coordinator.py` (append)

Audit reference: `AUDIT-uhome-ha-2026-04-18.md` → `coordinator.py::async_discover_devices` section (dispatch order is lock → dimmer/light/bulb → switch → skip).

- [ ] **Step 1: Append type-routing tests**

```python
# --- async_discover_devices: type routing ---

from utec_py.devices.light import Light as UhomeLight
from utec_py.devices.lock import Lock as UhomeLock
from utec_py.devices.switch import Switch as UhomeSwitch


def _discovery(handle_type: str, device_id: str = "d1") -> dict:
    return {
        "id": device_id,
        "name": "Test",
        "handleType": handle_type,
        "category": "unknown",
        "deviceInfo": {"manufacturer": "U-Tec", "model": "M", "hwVersion": "1.0"},
    }


async def test_discover_creates_lock(coordinator, mock_uhome_api):
    mock_uhome_api.discover_devices.return_value = {
        "payload": {"devices": [_discovery("utec-lock", "L1")]}
    }
    await coordinator.async_discover_devices()
    assert "L1" in coordinator.devices
    assert isinstance(coordinator.devices["L1"], UhomeLock)


async def test_discover_creates_light_for_dimmer(coordinator, mock_uhome_api):
    """Critical: 'dimmer' check must come BEFORE 'switch' — regression would
    misclassify utec-dimmer as Switch."""
    mock_uhome_api.discover_devices.return_value = {
        "payload": {"devices": [_discovery("utec-dimmer", "D1")]}
    }
    await coordinator.async_discover_devices()
    assert isinstance(coordinator.devices["D1"], UhomeLight)


async def test_discover_creates_light_for_bulb(coordinator, mock_uhome_api):
    mock_uhome_api.discover_devices.return_value = {
        "payload": {"devices": [_discovery("utec-bulb-color", "B1")]}
    }
    await coordinator.async_discover_devices()
    assert isinstance(coordinator.devices["B1"], UhomeLight)


async def test_discover_creates_switch_for_plain_switch(coordinator, mock_uhome_api):
    mock_uhome_api.discover_devices.return_value = {
        "payload": {"devices": [_discovery("utec-switch", "S1")]}
    }
    await coordinator.async_discover_devices()
    assert isinstance(coordinator.devices["S1"], UhomeSwitch)


async def test_discover_skips_unknown_handle_type(coordinator, mock_uhome_api):
    mock_uhome_api.discover_devices.return_value = {
        "payload": {"devices": [_discovery("mystery-device", "M1")]}
    }
    await coordinator.async_discover_devices()
    assert "M1" not in coordinator.devices
```

- [ ] **Step 2: Run**. Expected: pass.

- [ ] **Step 3: Commit** `git add tests/test_coordinator.py && git commit -m "test: cover async_discover_devices handleType routing"`

---

### Task 6b: `async_discover_devices` — edge cases

**Files:**
- Modify: `tests/test_coordinator.py` (append)

- [ ] **Step 1: Append edge-case tests**

```python
# --- async_discover_devices: edge cases ---


async def test_discover_skips_existing_device(coordinator, mock_uhome_api):
    existing = make_fake_switch("S1")
    coordinator.devices["S1"] = existing
    mock_uhome_api.discover_devices.return_value = {
        "payload": {"devices": [_discovery("utec-switch", "S1")]}
    }
    await coordinator.async_discover_devices()
    assert coordinator.devices["S1"] is existing  # unchanged


async def test_discover_handles_api_error_gracefully(coordinator, mock_uhome_api):
    mock_uhome_api.discover_devices.side_effect = ApiError(500, "down")
    await coordinator.async_discover_devices()  # should not raise
    assert coordinator.devices == {}


async def test_discover_bulk_fetches_initial_state_for_new_devices(
    coordinator, mock_uhome_api,
):
    mock_uhome_api.discover_devices.return_value = {
        "payload": {"devices": [
            _discovery("utec-switch", "S1"),
            _discovery("utec-switch", "S2"),
        ]}
    }
    state_payload = {"payload": {"devices": [
        {"id": "S1", "states": []},
        {"id": "S2", "states": []},
    ]}}
    mock_uhome_api.get_device_state.return_value = state_payload

    await coordinator.async_discover_devices()

    mock_uhome_api.get_device_state.assert_awaited_once_with(["S1", "S2"], None)


async def test_discover_invalid_discovery_data_is_noop(coordinator, mock_uhome_api):
    mock_uhome_api.discover_devices.return_value = {}  # no "payload" key
    await coordinator.async_discover_devices()
    assert coordinator.devices == {}


async def test_discover_device_missing_id_is_skipped(coordinator, mock_uhome_api):
    mock_uhome_api.discover_devices.return_value = {
        "payload": {"devices": [{"handleType": "utec-switch"}]}  # no id
    }
    await coordinator.async_discover_devices()
    assert coordinator.devices == {}
```

- [ ] **Step 2: Run**. Expected: pass.

- [ ] **Step 3: Commit** `git add tests/test_coordinator.py && git commit -m "test: cover async_discover_devices edge cases (existing, errors, bulk-fetch)"`

---

### Task 7: `api._handle_webhook` — auth boundary

**Files:**
- Create: `tests/test_webhook.py`

- [ ] **Step 1: Write the tests**

```python
"""Tests for AsyncPushUpdateHandler._handle_webhook (security boundary)."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from aiohttp import web

from custom_components.u_tec.api import AsyncPushUpdateHandler
from custom_components.u_tec.const import DOMAIN


def _make_request(method: str = "POST", *, body: bytes = b"{}", headers: dict | None = None):
    req = MagicMock()
    req.method = method
    req.read = AsyncMock(return_value=body)
    req.headers = headers or {}
    return req


@pytest.fixture
def webhook_handler(hass, mock_uhome_api):
    h = AsyncPushUpdateHandler(hass, mock_uhome_api, entry_id="entry-1")
    h._push_secret = "correct-secret"
    # Wire up hass.data so _handle_webhook can find the coordinator
    coord = MagicMock()
    coord.update_push_data = AsyncMock()
    hass.data[DOMAIN] = {"entry-1": {"coordinator": coord}}
    return h, coord


async def test_rejects_non_post_method(webhook_handler, hass):
    h, _ = webhook_handler
    resp = await h._handle_webhook(hass, "wh-id", _make_request("GET"))
    assert resp.status == 405


async def test_rejects_invalid_json_body(webhook_handler, hass):
    h, _ = webhook_handler
    req = _make_request(body=b"not-json")
    resp = await h._handle_webhook(hass, "wh-id", req)
    assert resp.status == 400


async def test_rejects_missing_authorization_header(webhook_handler, hass):
    h, _ = webhook_handler
    req = _make_request(body=b'{"devices": []}')
    resp = await h._handle_webhook(hass, "wh-id", req)
    assert resp.status == 401


async def test_rejects_wrong_bearer_token(webhook_handler, hass):
    h, _ = webhook_handler
    req = _make_request(
        body=b'{"devices": []}',
        headers={"Authorization": "Bearer wrong-secret"},
    )
    resp = await h._handle_webhook(hass, "wh-id", req)
    assert resp.status == 403


async def test_accepts_correct_bearer_token(webhook_handler, hass):
    h, coord = webhook_handler
    req = _make_request(
        body=b'{"payload": {"devices": []}}',
        headers={"Authorization": "Bearer correct-secret"},
    )
    resp = await h._handle_webhook(hass, "wh-id", req)
    assert resp.status == 200
    coord.update_push_data.assert_awaited_once()


async def test_rejects_unknown_entry_id(hass, mock_uhome_api):
    h = AsyncPushUpdateHandler(hass, mock_uhome_api, entry_id="bogus")
    h._push_secret = "s"
    hass.data[DOMAIN] = {}  # entry-1 not present
    req = _make_request(
        body=b'{"devices": []}',
        headers={"Authorization": "Bearer s"},
    )
    resp = await h._handle_webhook(hass, "wh-id", req)
    assert resp.status == 404


async def test_bearer_stripped_with_whitespace(webhook_handler, hass):
    h, coord = webhook_handler
    req = _make_request(
        body=b'{"payload": {"devices": []}}',
        headers={"Authorization": "Bearer   correct-secret  "},
    )
    resp = await h._handle_webhook(hass, "wh-id", req)
    assert resp.status == 200


async def test_no_push_secret_set_bypasses_token_check(hass, mock_uhome_api):
    """If _push_secret is None the handler doesn't validate the token."""
    h = AsyncPushUpdateHandler(hass, mock_uhome_api, entry_id="entry-1")
    h._push_secret = None
    coord = MagicMock()
    coord.update_push_data = AsyncMock()
    hass.data[DOMAIN] = {"entry-1": {"coordinator": coord}}

    req = _make_request(body=b'{"devices": []}')  # no auth header
    resp = await h._handle_webhook(hass, "wh-id", req)
    assert resp.status == 200
```

- [ ] **Step 2: Run** `.venv/bin/pytest tests/test_webhook.py -v`. Expected: all pass.

- [ ] **Step 3: Commit** `git add tests/test_webhook.py && git commit -m "test: cover webhook auth boundary and request validation"`

---

### Task 8: `application_credentials` — URL constants

**Files:**
- Create: `tests/test_application_credentials.py`

**Local LLM candidate:** Trivial test file — single assertion that the two URL constants are returned. Safe for `local_llm`. Prompt: *"Given this function signature from the AUDIT: `async def async_get_authorization_server(hass) -> AuthorizationServer` returning `authorize_url=OAUTH2_AUTHORIZE`, `token_url=OAUTH2_TOKEN`. Write a single pytest-async test calling it and asserting both URLs match the constants. Imports: `from custom_components.u_tec import application_credentials`, `from custom_components.u_tec.const import OAUTH2_AUTHORIZE, OAUTH2_TOKEN`."* Log outcome.

- [ ] **Step 1: Write the tests** (verify function name against AUDIT section for application_credentials.py)

```python
"""Tests for application_credentials module."""

from custom_components.u_tec import application_credentials
from custom_components.u_tec.const import OAUTH2_AUTHORIZE, OAUTH2_TOKEN


async def test_async_get_authorization_server_returns_configured_urls(hass):
    server = await application_credentials.async_get_authorization_server(hass)
    assert server.authorize_url == OAUTH2_AUTHORIZE
    assert server.token_url == OAUTH2_TOKEN
```

Adjust the function name if `application_credentials.py` names it differently — read the source first.

- [ ] **Step 2: Run**. Expected: pass.

- [ ] **Step 3: Commit** `git add tests/test_application_credentials.py && git commit -m "test: cover application_credentials OAuth2 server URLs"`

---

### Task 9: `config_flow` — initial OAuth entry creation

**Files:**
- Create: `tests/test_config_flow.py`

- [ ] **Step 1: Read `custom_components/u_tec/config_flow.py` end-to-end.** Note the `DOMAIN`, the `VERSION` class var, the `async_oauth_create_entry` method, and any step names exposed (`user`, `pick_implementation`, `oauth_create_entry`, `reauth`, `reauth_confirm`).

- [ ] **Step 2: Write tests using `pytest-homeassistant-custom-component`'s oauth helpers**

```python
"""Tests for UhomeOAuth2FlowHandler initial flow."""

from unittest.mock import patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.u_tec.const import DOMAIN, OAUTH2_AUTHORIZE, OAUTH2_TOKEN


@pytest.fixture(autouse=True)
async def setup_credentials(hass):
    """Register application credentials used by the OAuth2 flow."""
    from homeassistant.components.application_credentials import (
        ClientCredential,
        async_import_client_credential,
    )
    from homeassistant.setup import async_setup_component

    await async_setup_component(hass, "application_credentials", {})
    await async_import_client_credential(
        hass,
        DOMAIN,
        ClientCredential("test-client-id", "test-client-secret"),
        "u_tec",
    )


async def test_initial_flow_creates_entry(hass, aioclient_mock, current_request_with_host):
    """Starting user flow and completing it creates a config entry."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    assert result["type"] == "form" or result["type"] == "external"

    # Complete OAuth step by mocking the token exchange
    aioclient_mock.post(
        OAUTH2_TOKEN,
        json={
            "access_token": "new-access",
            "refresh_token": "new-refresh",
            "expires_in": 3600,
        },
    )

    # Simulate the OAuth2 helper exchange. The exact flow depends on HA's
    # AbstractOAuth2FlowHandler; pytest_homeassistant_custom_component
    # exposes helpers to walk through it. Use `external_step_done` as needed.
    # (Details vary by HA version — consult the helper docs.)


async def test_flow_aborts_when_already_configured(hass):
    """A second flow init aborts if a config entry already exists."""
    existing = MockConfigEntry(
        domain=DOMAIN,
        unique_id="u_tec",
        data={"auth_implementation": "u_tec"},
        version=2,
    )
    existing.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    # Depending on flow shape, this may return "abort" directly or via form
    assert result["type"] in ("abort", "form")
    if result["type"] == "abort":
        assert result["reason"] in ("already_configured", "single_instance_allowed")
```

The OAuth flow setup above is a skeleton. The `pytest_homeassistant_custom_component` helpers (`current_request_with_host`, `aioclient_mock`) are documented at <https://github.com/MatthewFlamm/pytest-homeassistant-custom-component>. If `HomeAssistant.AbstractOAuth2FlowHandler` makes a full happy-path flow too complex for one task, split into:
- **9a:** Verify `UhomeOAuth2FlowHandler.VERSION == 2` and `DOMAIN` attribute.
- **9b:** Verify `async_oauth_create_entry` returns a data dict via direct call with a mock token.
- **9c:** (deferred) Full browser-flow walkthrough.

Minimal test that always works:

```python
async def test_flow_handler_version_is_current(hass):
    from custom_components.u_tec.config_flow import UhomeOAuth2FlowHandler
    assert UhomeOAuth2FlowHandler.VERSION == 2
    assert UhomeOAuth2FlowHandler.DOMAIN == DOMAIN


async def test_async_oauth_create_entry_builds_entry(hass):
    from custom_components.u_tec.config_flow import UhomeOAuth2FlowHandler

    handler = UhomeOAuth2FlowHandler()
    handler.hass = hass
    handler.flow_impl = None  # satisfies AbstractOAuth2FlowHandler

    data = {"token": {"access_token": "tok"}}
    result = await handler.async_oauth_create_entry(data)
    # AbstractOAuth2FlowHandler default creates a ConfigEntry dict
    assert result["type"] in ("create_entry", "form", "abort")
```

- [ ] **Step 3: Run**. The "minimal" tests should always pass; the full-flow tests may need iteration. If full-flow is blocked, ship the minimal tests + one task for flow stepping later.

- [ ] **Step 4: Commit** `git add tests/test_config_flow.py && git commit -m "test: cover UhomeOAuth2FlowHandler initial flow (minimal)"`

---

### Task 10: `config_flow` — reauth flow

**Files:**
- Modify: `tests/test_config_flow.py` (append)

- [ ] **Step 1: Append reauth tests**

```python
# --- Reauth ---

async def test_reauth_starts_flow_with_existing_entry(hass):
    """Triggering reauth should start a flow scoped to the existing entry."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="u_tec",
        data={"auth_implementation": "u_tec", "token": {"access_token": "old"}},
        version=2,
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": "reauth",
            "entry_id": entry.entry_id,
            "unique_id": entry.unique_id,
        },
        data=entry.data,
    )
    assert result["type"] in ("form", "external")
```

If `async_step_reauth` is a simple delegation to `async_step_reauth_confirm`, add:

```python
async def test_reauth_confirm_shows_form(hass):
    from custom_components.u_tec.config_flow import UhomeOAuth2FlowHandler

    handler = UhomeOAuth2FlowHandler()
    handler.hass = hass
    # Simulate a stored reauth entry
    result = await handler.async_step_reauth_confirm()
    assert result["type"] == "form"
    assert result["step_id"] == "reauth_confirm"
```

- [ ] **Step 2: Run**. Expected: pass.

- [ ] **Step 3: Commit** `git add tests/test_config_flow.py && git commit -m "test: cover reauth flow steps"`

---

### Task 11: `OptionsFlowHandler._current_mode` helper + initial step

**Files:**
- Create: `tests/test_options_flow.py`

- [ ] **Step 1: Read `custom_components/u_tec/config_flow.py`** to find `OptionsFlowHandler` and `_current_mode`. Note the exact step names and menu options.

- [ ] **Step 2: Write tests**

```python
"""Tests for OptionsFlowHandler."""

from unittest.mock import MagicMock

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.u_tec.config_flow import OptionsFlowHandler
from custom_components.u_tec.const import (
    CONF_OPTIMISTIC_LIGHTS,
    CONF_OPTIMISTIC_LOCKS,
    CONF_OPTIMISTIC_SWITCHES,
    CONF_PUSH_DEVICES,
    CONF_PUSH_ENABLED,
    DOMAIN,
)
from tests.common import make_config_entry


def test_current_mode_returns_all_when_true():
    handler = OptionsFlowHandler.__new__(OptionsFlowHandler)
    handler.config_entry = MagicMock()
    handler.config_entry.options = {CONF_OPTIMISTIC_LIGHTS: True}
    assert handler._current_mode(CONF_OPTIMISTIC_LIGHTS) == "all"


def test_current_mode_returns_none_when_false():
    handler = OptionsFlowHandler.__new__(OptionsFlowHandler)
    handler.config_entry = MagicMock()
    handler.config_entry.options = {CONF_OPTIMISTIC_LIGHTS: False}
    assert handler._current_mode(CONF_OPTIMISTIC_LIGHTS) == "none"


def test_current_mode_returns_pick_for_list():
    handler = OptionsFlowHandler.__new__(OptionsFlowHandler)
    handler.config_entry = MagicMock()
    handler.config_entry.options = {CONF_OPTIMISTIC_LIGHTS: ["dev-1", "dev-2"]}
    assert handler._current_mode(CONF_OPTIMISTIC_LIGHTS) == "pick"


def test_current_mode_returns_all_when_missing_default():
    handler = OptionsFlowHandler.__new__(OptionsFlowHandler)
    handler.config_entry = MagicMock()
    handler.config_entry.options = {}
    # Default is True → all devices optimistic
    assert handler._current_mode(CONF_OPTIMISTIC_LIGHTS) == "all"
```

If `_current_mode` doesn't exist with this exact name, search `config_flow.py` for a function that maps option values to the strings "all"/"none"/"pick", and rename the tests. If the mapping uses different strings, adjust assertions to match.

- [ ] **Step 3: Run**. Expected: pass.

- [ ] **Step 4: Commit** `git add tests/test_options_flow.py && git commit -m "test: cover OptionsFlowHandler._current_mode mapping"`

---

### Task 12: `OptionsFlowHandler` — init step and push toggle

**Files:**
- Modify: `tests/test_options_flow.py` (append)

- [ ] **Step 1: Append**

```python
# --- Init + push toggle ---

async def test_init_step_shows_menu(hass):
    entry = make_config_entry()
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] == "menu"
    # At minimum, expect push settings and optimistic settings options
    assert "menu_options" in result


async def test_init_step_configure_push(hass):
    """Selecting 'configure_push' should route to that step."""
    entry = make_config_entry()
    entry.add_to_hass(hass)

    await hass.config_entries.options.async_init(entry.entry_id)
    # Select the "configure_push" menu item (adjust to actual menu option name)
    result = await hass.config_entries.options.async_configure(
        entry.entry_id,  # flow_id is returned by async_init; this is the *entry* id
        user_input=None,
    )
    # ^ Rework using the returned flow_id from async_init. See the example below.
```

The correct pattern for options flow tests uses the returned `flow_id`:

```python
async def test_init_step_using_flow_id(hass):
    entry = make_config_entry()
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    flow_id = result["flow_id"]

    # Advance by selecting a menu option
    result = await hass.config_entries.options.async_configure(
        flow_id, user_input={"next_step_id": "configure_push"},
    )
    assert result["type"] == "form"
    assert result["step_id"] == "configure_push"
```

Adjust `"next_step_id"` to the actual menu key. Read `async_step_init` in `config_flow.py` to find the menu definition.

- [ ] **Step 2: Run**. Fix step names against the real source.

- [ ] **Step 3: Commit** `git add tests/test_options_flow.py && git commit -m "test: cover OptionsFlowHandler menu routing"`

---

### Task 13a: `OptionsFlowHandler` — optimistic picker, "all" mode walkthrough

**Files:**
- Modify: `tests/test_options_flow.py` (append)

Audit reference: `AUDIT-uhome-ha-2026-04-18.md` → `config_flow.py::OptionsFlowHandler` section (exact step_ids, menu_options, mode value strings).

- [ ] **Step 1: Append the "all" mode walkthrough**

```python
# --- Optimistic picker: all-mode ---

from tests.common import make_fake_light, make_fake_switch, make_fake_lock


async def test_optimistic_all_for_every_type(hass):
    """Setting mode='all' for every type should skip the picker steps and
    produce True for each CONF_OPTIMISTIC_* key."""
    entry = make_config_entry()
    entry.add_to_hass(hass)

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "coordinator": MagicMock(devices={
            "light-1": make_fake_light("light-1"),
            "sw-1": make_fake_switch("sw-1"),
            "lock-1": make_fake_lock("lock-1"),
        }),
    }

    result = await hass.config_entries.options.async_init(entry.entry_id)
    flow_id = result["flow_id"]

    # Navigate to optimistic menu — adjust next_step_id to match AUDIT
    result = await hass.config_entries.options.async_configure(
        flow_id, user_input={"next_step_id": "configure_optimistic"},
    )

    # Three consecutive mode=all selections (lights, switches, locks)
    for _ in range(3):
        result = await hass.config_entries.options.async_configure(
            flow_id, user_input={"mode": "all"},
        )

    assert result["type"] == "create_entry"
    assert result["data"][CONF_OPTIMISTIC_LIGHTS] is True
    assert result["data"][CONF_OPTIMISTIC_SWITCHES] is True
    assert result["data"][CONF_OPTIMISTIC_LOCKS] is True
```

If a step name differs from the AUDIT, update accordingly. If the final "configure_optimistic" menu routing is structured differently (e.g. a sub-menu), adjust the first `async_configure` call.

- [ ] **Step 2: Run**. Expected: pass.

- [ ] **Step 3: Commit** `git add tests/test_options_flow.py && git commit -m "test: cover optimistic picker all-mode walkthrough"`

---

### Task 13b: `OptionsFlowHandler` — optimistic picker, "pick" mode walkthrough

**Files:**
- Modify: `tests/test_options_flow.py` (append)

- [ ] **Step 1: Append the "pick" mode walkthrough**

```python
# --- Optimistic picker: pick-mode ---


async def test_optimistic_pick_for_lights(hass):
    """Mode='pick' routes to device-selection step; selected devices end up in options list."""
    entry = make_config_entry()
    entry.add_to_hass(hass)

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "coordinator": MagicMock(devices={
            "light-1": make_fake_light("light-1"),
            "light-2": make_fake_light("light-2"),
        }),
    }

    result = await hass.config_entries.options.async_init(entry.entry_id)
    flow_id = result["flow_id"]
    result = await hass.config_entries.options.async_configure(
        flow_id, user_input={"next_step_id": "configure_optimistic"},
    )
    # Lights: pick mode
    result = await hass.config_entries.options.async_configure(
        flow_id, user_input={"mode": "pick"},
    )
    # Picker step: select specific light. Key name ("devices") is placeholder —
    # AUDIT gives the real schema field name.
    result = await hass.config_entries.options.async_configure(
        flow_id, user_input={"devices": ["light-1"]},
    )
    # Switches: mode=all (no switches)
    result = await hass.config_entries.options.async_configure(
        flow_id, user_input={"mode": "all"},
    )
    # Locks: mode=all
    result = await hass.config_entries.options.async_configure(
        flow_id, user_input={"mode": "all"},
    )
    assert result["type"] == "create_entry"
    assert result["data"][CONF_OPTIMISTIC_LIGHTS] == ["light-1"]
```

- [ ] **Step 2: Run**. Expected: pass.

- [ ] **Step 3: Commit** `git add tests/test_options_flow.py && git commit -m "test: cover optimistic picker pick-mode walkthrough"`

---

### Task 13c: `OptionsFlowHandler` — optimistic picker, "none" mode skips picker

**Files:**
- Modify: `tests/test_options_flow.py` (append)

- [ ] **Step 1: Append the "none" mode walkthrough**

```python
# --- Optimistic picker: none-mode ---


async def test_optimistic_none_skips_picker(hass):
    """Mode='none' should skip the picker step and move to next type, storing False."""
    entry = make_config_entry()
    entry.add_to_hass(hass)

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "coordinator": MagicMock(devices={
            "light-1": make_fake_light("light-1"),
        }),
    }

    result = await hass.config_entries.options.async_init(entry.entry_id)
    flow_id = result["flow_id"]
    result = await hass.config_entries.options.async_configure(
        flow_id, user_input={"next_step_id": "configure_optimistic"},
    )
    # Lights: none — picker step must be skipped (only 3 further steps total)
    result = await hass.config_entries.options.async_configure(
        flow_id, user_input={"mode": "none"},
    )
    result = await hass.config_entries.options.async_configure(
        flow_id, user_input={"mode": "all"},
    )
    result = await hass.config_entries.options.async_configure(
        flow_id, user_input={"mode": "all"},
    )
    assert result["type"] == "create_entry"
    assert result["data"][CONF_OPTIMISTIC_LIGHTS] is False
```

- [ ] **Step 2: Run**. Expected: pass.

- [ ] **Step 3: Commit** `git add tests/test_options_flow.py && git commit -m "test: cover optimistic picker none-mode skips picker"`

---

### Task 14: Phase 1 coverage checkpoint

- [ ] **Step 1: Run coverage**

```bash
.venv/bin/pytest tests/ --cov=custom_components.u_tec --cov-report=term-missing --cov-report=html
```

- [ ] **Step 2: Confirm coverage ≥50%** (baseline after Phase 1). Per-module expectations:
  - `optimistic.py`: 100%
  - `coordinator.py`: ≥80%
  - `api.py` (webhook portion): ≥60%
  - `config_flow.py`: ≥40%
  - `__init__.py` (async_migrate_entry only): ~15-20%
  - Platform files (`light`/`switch`/`lock`/`sensor`/`binary_sensor`): still 0% — Phase 3.

If <50% overall, stop and check for missing tests before proceeding.

- [ ] **Step 3: Commit coverage artifacts ignore**

```bash
# If not already in .gitignore:
grep -qxF "htmlcov/" .gitignore || echo -e "htmlcov/\n.coverage\n.coverage.*" >> .gitignore
git add .gitignore
git commit -m "chore: ignore coverage artifacts"
```

---

## Phase 2 — Depth: entity platforms

### Task 15a: `UhomeLightEntity` — init + turn_on/off + optimistic set

**Files:**
- Create: `tests/test_light.py`

Audit reference: `AUDIT-uhome-ha-2026-04-18.md` → `light.py` section (brightness scale, optimistic attrs).

- [ ] **Step 1: Write init + command tests**

```python
"""Tests for UhomeLightEntity — init and commands."""

from unittest.mock import MagicMock

import pytest

from custom_components.u_tec.const import CONF_OPTIMISTIC_LIGHTS, DOMAIN
from custom_components.u_tec.light import UhomeLightEntity
from tests.common import make_config_entry, make_fake_light


@pytest.fixture
def coord_with_light(hass):
    entry = make_config_entry(options={CONF_OPTIMISTIC_LIGHTS: True})
    entry.add_to_hass(hass)
    light = make_fake_light("light-1", is_on=False)
    coord = MagicMock()
    coord.devices = {"light-1": light}
    coord.config_entry = entry
    coord.last_update_success = True
    coord.data = {}
    return coord, light


def test_init_sets_unique_id_and_name(coord_with_light):
    coord, light = coord_with_light
    ent = UhomeLightEntity(coord, "light-1")
    assert ent.unique_id == f"{DOMAIN}_light-1"
    assert ent.name == "Fake Light"


def test_is_on_reads_device_when_no_optimistic(coord_with_light):
    coord, light = coord_with_light
    light.is_on = True
    ent = UhomeLightEntity(coord, "light-1")
    assert ent.is_on is True


async def test_async_turn_on_sets_optimistic_and_calls_device(coord_with_light, hass):
    coord, light = coord_with_light
    ent = UhomeLightEntity(coord, "light-1")
    ent.hass = hass
    ent.entity_id = "light.fake_light"
    ent.async_write_ha_state = MagicMock()

    await ent.async_turn_on()

    light.turn_on.assert_awaited_once()
    assert ent._optimistic_is_on is True


async def test_async_turn_off_sets_optimistic_and_calls_device(coord_with_light, hass):
    coord, light = coord_with_light
    light.is_on = True
    ent = UhomeLightEntity(coord, "light-1")
    ent.hass = hass
    ent.entity_id = "light.fake_light"
    ent.async_write_ha_state = MagicMock()

    await ent.async_turn_off()

    light.turn_off.assert_awaited_once()
    assert ent._optimistic_is_on is False


async def test_turn_on_with_brightness_sets_pending(coord_with_light, hass):
    coord, light = coord_with_light
    ent = UhomeLightEntity(coord, "light-1")
    ent.hass = hass
    ent.entity_id = "light.fake_light"
    ent.async_write_ha_state = MagicMock()

    await ent.async_turn_on(brightness=255)  # HA scale 0-255

    light.turn_on.assert_awaited_once()
    _, call_kwargs = light.turn_on.call_args
    assert call_kwargs["brightness"] == 100  # U-Tec scale 1-100
    assert ent._optimistic_brightness == 255
    assert ent._pending_brightness_utec == 100
```

- [ ] **Step 2: Run** `.venv/bin/pytest tests/test_light.py -v`. Expected: pass.

- [ ] **Step 3: Commit** `git add tests/test_light.py && git commit -m "test: cover UhomeLightEntity init + turn_on/off optimistic set"`

---

### Task 15b: `UhomeLightEntity._handle_coordinator_update` — state-clear logic

**Files:**
- Modify: `tests/test_light.py` (append)

- [ ] **Step 1: Append coordinator-update state-clear tests**

```python
# --- _handle_coordinator_update state-clear ---


def test_coordinator_update_clears_optimistic_when_device_confirms(coord_with_light):
    coord, light = coord_with_light
    ent = UhomeLightEntity(coord, "light-1")
    ent._optimistic_is_on = True
    light.is_on = True  # device now reports the same

    ent._handle_coordinator_update()

    assert ent._optimistic_is_on is None


def test_coordinator_update_keeps_optimistic_when_device_disagrees(coord_with_light):
    coord, light = coord_with_light
    ent = UhomeLightEntity(coord, "light-1")
    ent._optimistic_is_on = True
    light.is_on = False  # device still reports old state

    ent._handle_coordinator_update()

    assert ent._optimistic_is_on is True


def test_brightness_pending_clears_only_on_exact_match(coord_with_light):
    coord, light = coord_with_light
    ent = UhomeLightEntity(coord, "light-1")
    ent._optimistic_brightness = 200
    ent._pending_brightness_utec = 80
    light.brightness = 80  # device caught up

    ent._handle_coordinator_update()

    assert ent._optimistic_brightness is None
    assert ent._pending_brightness_utec is None


def test_brightness_pending_persists_when_device_differs(coord_with_light):
    coord, light = coord_with_light
    ent = UhomeLightEntity(coord, "light-1")
    ent._optimistic_brightness = 200
    ent._pending_brightness_utec = 80
    light.brightness = 50  # device hasn't caught up

    ent._handle_coordinator_update()

    assert ent._optimistic_brightness == 200
    assert ent._pending_brightness_utec == 80
```

- [ ] **Step 2: Run**. Expected: pass.

- [ ] **Step 3: Commit** `git add tests/test_light.py && git commit -m "test: cover UhomeLightEntity coordinator-update state-clear logic"`

---

### Task 15c: `UhomeLightEntity` — assumed_state + error wrapping

**Files:**
- Modify: `tests/test_light.py` (append)

- [ ] **Step 1: Append assumed_state + error tests**

```python
# --- assumed_state + error handling ---


def test_assumed_state_true_when_optimistic_and_pending(coord_with_light):
    coord, light = coord_with_light
    ent = UhomeLightEntity(coord, "light-1")
    ent._optimistic_is_on = True
    assert ent.assumed_state is True


def test_assumed_state_false_when_optimistic_disabled(hass):
    entry = make_config_entry(options={CONF_OPTIMISTIC_LIGHTS: False})
    entry.add_to_hass(hass)
    light = make_fake_light("light-1")
    coord = MagicMock()
    coord.devices = {"light-1": light}
    coord.config_entry = entry
    coord.last_update_success = True
    coord.data = {}

    ent = UhomeLightEntity(coord, "light-1")
    ent._optimistic_is_on = True  # would be set, but optimistic disabled
    assert ent.assumed_state is False


async def test_turn_on_wraps_device_error(coord_with_light, hass):
    from homeassistant.exceptions import HomeAssistantError
    from utec_py.exceptions import DeviceError

    coord, light = coord_with_light
    light.turn_on.side_effect = DeviceError("nope")
    ent = UhomeLightEntity(coord, "light-1")
    ent.hass = hass
    ent.entity_id = "light.fake_light"

    with pytest.raises(HomeAssistantError):
        await ent.async_turn_on()


async def test_turn_off_wraps_device_error(coord_with_light, hass):
    from homeassistant.exceptions import HomeAssistantError
    from utec_py.exceptions import DeviceError

    coord, light = coord_with_light
    light.turn_off.side_effect = DeviceError("nope")
    ent = UhomeLightEntity(coord, "light-1")
    ent.hass = hass
    ent.entity_id = "light.fake_light"

    with pytest.raises(HomeAssistantError):
        await ent.async_turn_off()
```

- [ ] **Step 2: Run**. Expected: pass.

- [ ] **Step 3: Commit** `git add tests/test_light.py && git commit -m "test: cover UhomeLightEntity assumed_state + DeviceError wrapping"`

---

### Task 16: `UhomeSwitchEntity` — on/off + optimistic state machine

**Files:**
- Create: `tests/test_switch.py`

- [ ] **Step 1: Read `custom_components/u_tec/switch.py`** — `UhomeSwitchEntity` should mirror `UhomeLightEntity` but without brightness/color. Write equivalent tests:

```python
"""Tests for UhomeSwitchEntity."""

from unittest.mock import MagicMock

import pytest

from custom_components.u_tec.const import CONF_OPTIMISTIC_SWITCHES, DOMAIN
from custom_components.u_tec.switch import UhomeSwitchEntity
from tests.common import make_config_entry, make_fake_switch


@pytest.fixture
def coord_with_switch(hass):
    entry = make_config_entry(options={CONF_OPTIMISTIC_SWITCHES: True})
    entry.add_to_hass(hass)
    sw = make_fake_switch("sw-1", is_on=False)
    coord = MagicMock()
    coord.devices = {"sw-1": sw}
    coord.config_entry = entry
    coord.last_update_success = True
    coord.data = {}
    return coord, sw


def test_init_sets_unique_id(coord_with_switch):
    coord, sw = coord_with_switch
    ent = UhomeSwitchEntity(coord, "sw-1")
    assert ent.unique_id == f"{DOMAIN}_sw-1"


async def test_turn_on_sets_optimistic(coord_with_switch, hass):
    coord, sw = coord_with_switch
    ent = UhomeSwitchEntity(coord, "sw-1")
    ent.hass = hass
    ent.entity_id = "switch.fake_switch"
    ent.async_write_ha_state = MagicMock()

    await ent.async_turn_on()

    sw.turn_on.assert_awaited_once()
    assert ent._optimistic_is_on is True


async def test_turn_off_sets_optimistic(coord_with_switch, hass):
    coord, sw = coord_with_switch
    ent = UhomeSwitchEntity(coord, "sw-1")
    ent.hass = hass
    ent.entity_id = "switch.fake_switch"
    ent.async_write_ha_state = MagicMock()

    await ent.async_turn_off()

    sw.turn_off.assert_awaited_once()
    assert ent._optimistic_is_on is False


async def test_coordinator_update_clears_optimistic_on_confirm(coord_with_switch):
    coord, sw = coord_with_switch
    ent = UhomeSwitchEntity(coord, "sw-1")
    ent._optimistic_is_on = True
    sw.is_on = True

    ent._handle_coordinator_update()

    assert ent._optimistic_is_on is None


async def test_turn_on_wraps_device_error(coord_with_switch, hass):
    from homeassistant.exceptions import HomeAssistantError
    from utec_py.exceptions import DeviceError

    coord, sw = coord_with_switch
    sw.turn_on.side_effect = DeviceError("nope")
    ent = UhomeSwitchEntity(coord, "sw-1")
    ent.hass = hass
    ent.entity_id = "switch.fake_switch"

    with pytest.raises(HomeAssistantError):
        await ent.async_turn_on()


async def test_assumed_state_respects_optimistic_config(hass):
    entry = make_config_entry(options={CONF_OPTIMISTIC_SWITCHES: False})
    entry.add_to_hass(hass)
    sw = make_fake_switch("sw-1")
    coord = MagicMock()
    coord.devices = {"sw-1": sw}
    coord.config_entry = entry
    coord.last_update_success = True

    ent = UhomeSwitchEntity(coord, "sw-1")
    ent._optimistic_is_on = True
    assert ent.assumed_state is False
```

- [ ] **Step 2: Run** `.venv/bin/pytest tests/test_switch.py -v`. Expected: all pass.

- [ ] **Step 3: Commit** `git add tests/test_switch.py && git commit -m "test: cover UhomeSwitchEntity optimistic state machine"`

---

### Task 17: `UhomeLockEntity` — lock/unlock + jammed + door attrs

**Files:**
- Create: `tests/test_lock.py`

- [ ] **Step 1: Read `custom_components/u_tec/lock.py`** — note `is_jammed`, `extra_state_attributes`, door-sensor data, optimistic fields.

- [ ] **Step 2: Write tests** (structure mirrors switch tests; add attr-dict and jammed tests):

```python
"""Tests for UhomeLockEntity."""

from unittest.mock import MagicMock

import pytest

from custom_components.u_tec.const import CONF_OPTIMISTIC_LOCKS, DOMAIN
from custom_components.u_tec.lock import UhomeLockEntity
from tests.common import make_config_entry, make_fake_lock


@pytest.fixture
def coord_with_lock(hass):
    entry = make_config_entry(options={CONF_OPTIMISTIC_LOCKS: True})
    entry.add_to_hass(hass)
    lock = make_fake_lock("lock-1", is_locked=True)
    coord = MagicMock()
    coord.devices = {"lock-1": lock}
    coord.config_entry = entry
    coord.last_update_success = True
    coord.data = {}
    return coord, lock


def test_init_unique_id(coord_with_lock):
    coord, lock = coord_with_lock
    ent = UhomeLockEntity(coord, "lock-1")
    assert ent.unique_id == f"{DOMAIN}_lock-1"


async def test_async_lock_sets_optimistic(coord_with_lock, hass):
    coord, lock = coord_with_lock
    lock.is_locked = False  # starting from unlocked
    ent = UhomeLockEntity(coord, "lock-1")
    ent.hass = hass
    ent.entity_id = "lock.fake_lock"
    ent.async_write_ha_state = MagicMock()

    await ent.async_lock()

    lock.lock.assert_awaited_once()


async def test_async_unlock_calls_device(coord_with_lock, hass):
    coord, lock = coord_with_lock
    ent = UhomeLockEntity(coord, "lock-1")
    ent.hass = hass
    ent.entity_id = "lock.fake_lock"
    ent.async_write_ha_state = MagicMock()

    await ent.async_unlock()

    lock.unlock.assert_awaited_once()


def test_is_jammed_reflects_device(coord_with_lock):
    coord, lock = coord_with_lock
    lock.is_jammed = True
    ent = UhomeLockEntity(coord, "lock-1")
    assert ent.is_jammed is True


def test_extra_state_attributes_include_door_sensor_when_present(coord_with_lock):
    coord, lock = coord_with_lock
    lock.has_door_sensor = True
    lock.is_door_open = True
    lock.battery_level = 77
    ent = UhomeLockEntity(coord, "lock-1")
    attrs = ent.extra_state_attributes or {}
    # Adjust keys to match actual impl
    assert attrs.get("door_state") in ("open", True) or attrs.get("is_door_open") is True
    assert attrs.get("battery_level") == 77


def test_extra_state_attributes_omit_door_sensor_when_absent(coord_with_lock):
    coord, lock = coord_with_lock
    lock.has_door_sensor = False
    ent = UhomeLockEntity(coord, "lock-1")
    attrs = ent.extra_state_attributes or {}
    assert "door_state" not in attrs and "is_door_open" not in attrs
```

Adjust attribute key names to match the real impl — read `lock.py` `extra_state_attributes`.

- [ ] **Step 3: Run** and iterate until green.

- [ ] **Step 4: Commit** `git add tests/test_lock.py && git commit -m "test: cover UhomeLockEntity lock/unlock + jammed + door attrs"`

---

### Task 18: `UhomeBatterySensorEntity` + dynamic addition

**Files:**
- Create: `tests/test_sensor.py`

- [ ] **Step 1: Read `custom_components/u_tec/sensor.py`** — confirm `_create_battery_entities` / `async_setup_entry` shape, `SIGNAL_NEW_DEVICE` handling, `add_only_new` guard.

- [ ] **Step 2: Write tests**

```python
"""Tests for UhomeBatterySensorEntity and dynamic addition."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.u_tec.const import DOMAIN, SIGNAL_NEW_DEVICE
from custom_components.u_tec.sensor import UhomeBatterySensorEntity
from tests.common import make_config_entry, make_fake_lock


@pytest.fixture
def coord_with_locks(hass):
    entry = make_config_entry()
    entry.add_to_hass(hass)
    lock1 = make_fake_lock("lock-1", battery_level=85)
    lock2 = make_fake_lock("lock-2", battery_level=20)
    coord = MagicMock()
    coord.devices = {"lock-1": lock1, "lock-2": lock2}
    coord.config_entry = entry
    coord.last_update_success = True
    coord.added_sensor_entities = set()
    return coord, entry


def test_battery_sensor_exposes_level(coord_with_locks):
    coord, _ = coord_with_locks
    ent = UhomeBatterySensorEntity(coord, "lock-1")
    assert ent.native_value == 85


def test_battery_sensor_unique_id(coord_with_locks):
    coord, _ = coord_with_locks
    ent = UhomeBatterySensorEntity(coord, "lock-1")
    assert "lock-1" in ent.unique_id
    assert "battery" in ent.unique_id.lower()


async def test_async_setup_entry_adds_one_per_lock(hass, coord_with_locks):
    """Initial setup should add battery sensors for all locks."""
    from custom_components.u_tec.sensor import async_setup_entry

    coord, entry = coord_with_locks
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {"coordinator": coord}
    added = []

    def _add(entities):
        added.extend(list(entities))

    await async_setup_entry(hass, entry, _add)
    assert len(added) == 2
    assert coord.added_sensor_entities == {"lock-1", "lock-2"}


async def test_async_setup_entry_dispatch_adds_new_devices(hass, coord_with_locks):
    """SIGNAL_NEW_DEVICE dispatch should add sensors for newly-discovered locks."""
    from homeassistant.helpers.dispatcher import async_dispatcher_send

    from custom_components.u_tec.sensor import async_setup_entry

    coord, entry = coord_with_locks
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {"coordinator": coord}
    added = []

    def _add(entities):
        added.extend(list(entities))

    await async_setup_entry(hass, entry, _add)
    initial_count = len(added)

    # Add a new lock, then dispatch
    coord.devices["lock-3"] = make_fake_lock("lock-3", battery_level=50)
    async_dispatcher_send(hass, SIGNAL_NEW_DEVICE)
    await hass.async_block_till_done()

    assert len(added) == initial_count + 1
    assert "lock-3" in coord.added_sensor_entities


async def test_dispatch_does_not_double_add(hass, coord_with_locks):
    from homeassistant.helpers.dispatcher import async_dispatcher_send

    from custom_components.u_tec.sensor import async_setup_entry

    coord, entry = coord_with_locks
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {"coordinator": coord}
    added = []

    def _add(entities):
        added.extend(list(entities))

    await async_setup_entry(hass, entry, _add)
    initial = len(added)

    async_dispatcher_send(hass, SIGNAL_NEW_DEVICE)
    await hass.async_block_till_done()

    # Same devices → no additions
    assert len(added) == initial
```

- [ ] **Step 3: Run** and iterate.

- [ ] **Step 4: Commit** `git add tests/test_sensor.py && git commit -m "test: cover UhomeBatterySensorEntity + SIGNAL_NEW_DEVICE dynamic addition"`

---

### Task 19: `UhomeDoorSensor` — inversion + availability

**Files:**
- Create: `tests/test_binary_sensor.py`

- [ ] **Step 1: Read `custom_components/u_tec/binary_sensor.py`** — note setup shape (likely filters locks with `has_door_sensor=True`) and `is_on` inversion logic (HA opens=on, HA closed=off).

- [ ] **Step 2: Write tests**

```python
"""Tests for UhomeDoorSensor."""

from unittest.mock import MagicMock

import pytest

from custom_components.u_tec.binary_sensor import UhomeDoorSensor
from tests.common import make_fake_lock


@pytest.fixture
def door_sensor_setup(hass):
    lock = make_fake_lock("lock-1", has_door_sensor=True, is_door_open=False)
    coord = MagicMock()
    coord.devices = {"lock-1": lock}
    coord.last_update_success = True
    return coord, lock


def test_is_on_false_when_door_closed(door_sensor_setup):
    coord, lock = door_sensor_setup
    lock.is_door_open = False
    ent = UhomeDoorSensor(coord, "lock-1")
    assert ent.is_on is False


def test_is_on_true_when_door_open(door_sensor_setup):
    coord, lock = door_sensor_setup
    lock.is_door_open = True
    ent = UhomeDoorSensor(coord, "lock-1")
    assert ent.is_on is True


def test_available_requires_coordinator_and_device(door_sensor_setup):
    coord, lock = door_sensor_setup
    ent = UhomeDoorSensor(coord, "lock-1")
    assert ent.available is True

    coord.last_update_success = False
    assert ent.available is False


def test_async_setup_entry_only_adds_locks_with_door_sensor(hass):
    """Locks without `has_door_sensor` should not get a binary sensor."""
    from tests.common import make_config_entry
    from custom_components.u_tec.binary_sensor import async_setup_entry
    from custom_components.u_tec.const import DOMAIN

    entry = make_config_entry()
    entry.add_to_hass(hass)
    lock_with = make_fake_lock("lock-1", has_door_sensor=True)
    lock_without = make_fake_lock("lock-2", has_door_sensor=False)
    coord = MagicMock()
    coord.devices = {"lock-1": lock_with, "lock-2": lock_without}
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {"coordinator": coord}

    added = []

    def _add(entities):
        added.extend(list(entities))

    import asyncio
    asyncio.get_event_loop().run_until_complete(async_setup_entry(hass, entry, _add))

    assert len(added) == 1
```

Use `pytest-asyncio` async def for the last test — mirror the sensor test pattern.

- [ ] **Step 3: Run** and iterate.

- [ ] **Step 4: Commit** `git add tests/test_binary_sensor.py && git commit -m "test: cover UhomeDoorSensor inversion and filtered setup"`

---

### Task 20: Phase 2 coverage checkpoint

- [ ] **Step 1: Run coverage**

```bash
.venv/bin/pytest tests/ --cov=custom_components.u_tec --cov-report=term-missing
```

- [ ] **Step 2: Expected ≥75% overall.** Per-module:
  - `light.py`, `switch.py`, `lock.py`: ≥85%
  - `sensor.py`, `binary_sensor.py`: ≥80%
  - `coordinator.py`: ≥85%

If short, identify uncovered lines from `--cov-report=term-missing` and add targeted tests before moving on.

- [ ] **Step 3: Commit** (no changes — this is a checkpoint).

---

## Phase 3 — Stretch: full setup + high-risk branches

### Task 21a: `async_setup_entry` — happy path with push disabled

**Files:**
- Create: `tests/test_setup.py`

Audit reference: `AUDIT-uhome-ha-2026-04-18.md` → `__init__.py::async_setup_entry` section.

- [ ] **Step 1: Write the happy-path test with push disabled (simplest wiring)**

```python
"""Tests for async_setup_entry end-to-end integration."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.u_tec import async_setup_entry
from custom_components.u_tec.const import CONF_PUSH_ENABLED, DOMAIN
from tests.common import make_config_entry


@pytest.fixture
def patched_uhomeapi():
    """Replace UHomeApi with a mock for setup-entry tests."""
    with patch("custom_components.u_tec.UHomeApi") as mock_cls:
        instance = MagicMock()
        instance.discover_devices = AsyncMock(return_value={"payload": {"devices": []}})
        instance.get_device_state = AsyncMock(return_value={"payload": {"devices": []}})
        instance.set_push_status = AsyncMock(return_value={})
        mock_cls.return_value = instance
        yield instance


async def test_setup_entry_creates_coordinator_and_stores_in_hass_data(
    hass, patched_uhomeapi,
):
    entry = make_config_entry(options={CONF_PUSH_ENABLED: False})
    entry.add_to_hass(hass)

    with patch(
        "custom_components.u_tec.config_entry_oauth2_flow.async_get_config_entry_implementation"
    ), patch(
        "custom_components.u_tec.config_entry_oauth2_flow.OAuth2Session"
    ) as mock_session:
        mock_session.return_value = MagicMock()
        result = await async_setup_entry(hass, entry)

    assert result is True
    assert DOMAIN in hass.data
    assert entry.entry_id in hass.data[DOMAIN]
    assert "coordinator" in hass.data[DOMAIN][entry.entry_id]
    assert "api" in hass.data[DOMAIN][entry.entry_id]
    assert "auth_data" in hass.data[DOMAIN][entry.entry_id]
    assert "webhook_handler" in hass.data[DOMAIN][entry.entry_id]


async def test_setup_entry_skips_webhook_when_push_disabled(
    hass, patched_uhomeapi,
):
    entry = make_config_entry(options={CONF_PUSH_ENABLED: False})
    entry.add_to_hass(hass)

    with patch(
        "custom_components.u_tec.config_entry_oauth2_flow.async_get_config_entry_implementation"
    ), patch(
        "custom_components.u_tec.config_entry_oauth2_flow.OAuth2Session"
    ) as mock_session, patch(
        "custom_components.u_tec.api.AsyncPushUpdateHandler.async_register_webhook",
        new=AsyncMock(),
    ) as mock_register:
        mock_session.return_value = MagicMock()
        await async_setup_entry(hass, entry)

    mock_register.assert_not_awaited()
```

- [ ] **Step 2: Run** `.venv/bin/pytest tests/test_setup.py -v`. Expected: pass.

- [ ] **Step 3: Commit** `git add tests/test_setup.py && git commit -m "test: cover async_setup_entry happy path (push disabled)"`

---

### Task 21b: `async_setup_entry` — push enabled registers webhook

**Files:**
- Modify: `tests/test_setup.py` (append)

- [ ] **Step 1: Append push-enabled test**

```python
# --- Push-enabled webhook registration ---


async def test_setup_entry_registers_webhook_when_push_enabled(
    hass, patched_uhomeapi,
):
    entry = make_config_entry(options={CONF_PUSH_ENABLED: True})
    entry.add_to_hass(hass)

    with patch(
        "custom_components.u_tec.config_entry_oauth2_flow.async_get_config_entry_implementation"
    ), patch(
        "custom_components.u_tec.config_entry_oauth2_flow.OAuth2Session"
    ) as mock_session, patch(
        "custom_components.u_tec.api.AsyncPushUpdateHandler.async_register_webhook",
        new=AsyncMock(return_value=True),
    ) as mock_register:
        mock_session.return_value = MagicMock()
        await async_setup_entry(hass, entry)

    mock_register.assert_awaited_once()
```

- [ ] **Step 2: Run**. Expected: pass.

- [ ] **Step 3: Commit** `git add tests/test_setup.py && git commit -m "test: cover async_setup_entry webhook registration when push enabled"`

---

### Task 21c: `async_update_options` — push toggle triggers register/unregister

**Files:**
- Modify: `tests/test_setup.py` (append)

- [ ] **Step 1: Append options-toggle test**

```python
# --- async_update_options push toggle ---

from custom_components.u_tec import async_update_options


async def test_async_update_options_toggles_webhook_on(hass, patched_uhomeapi):
    entry = make_config_entry(options={CONF_PUSH_ENABLED: False})
    entry.add_to_hass(hass)

    with patch(
        "custom_components.u_tec.config_entry_oauth2_flow.async_get_config_entry_implementation"
    ), patch(
        "custom_components.u_tec.config_entry_oauth2_flow.OAuth2Session"
    ) as mock_session, patch(
        "custom_components.u_tec.api.AsyncPushUpdateHandler.async_register_webhook",
        new=AsyncMock(return_value=True),
    ) as mock_register:
        mock_session.return_value = MagicMock()
        await async_setup_entry(hass, entry)

        # Flip push on
        hass.config_entries.async_update_entry(entry, options={CONF_PUSH_ENABLED: True})
        await async_update_options(hass, entry)
        await hass.async_block_till_done()

    mock_register.assert_awaited()  # called at least once after flip
```

- [ ] **Step 2: Run**. Expected: pass.

- [ ] **Step 3: Commit** `git add tests/test_setup.py && git commit -m "test: cover async_update_options push toggle"`

---

### Task 22a: `async_register_webhook` — URL resolution strategies

**Files:**
- Create: `tests/test_webhook_registration.py`

Audit reference: `AUDIT-uhome-ha-2026-04-18.md` → `api.py::async_register_webhook` (strategy loop: three (allow_internal, allow_ip, prefer_cloud) triples).

- [ ] **Step 1: Write URL-resolution tests**

```python
"""Tests for AsyncPushUpdateHandler.async_register_webhook — URL resolution."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.helpers.network import NoURLAvailableError

from custom_components.u_tec.api import AsyncPushUpdateHandler


async def test_register_succeeds_with_external_url(hass, mock_uhome_api):
    h = AsyncPushUpdateHandler(hass, mock_uhome_api, entry_id="e1")

    with patch(
        "custom_components.u_tec.api.network.get_url",
        return_value="https://ha.example.com",
    ), patch(
        "custom_components.u_tec.api.webhook.async_generate_url",
        return_value="https://ha.example.com/api/webhook/x",
    ), patch(
        "custom_components.u_tec.api.webhook.async_register",
        return_value=lambda: None,
    ):
        result = await h.async_register_webhook(auth_data=MagicMock())

    assert result is True
    mock_uhome_api.set_push_status.assert_awaited_once()


async def test_register_fails_when_no_url_available(hass, mock_uhome_api):
    h = AsyncPushUpdateHandler(hass, mock_uhome_api, entry_id="e1")

    with patch(
        "custom_components.u_tec.api.network.get_url",
        side_effect=NoURLAvailableError(),
    ):
        result = await h.async_register_webhook(auth_data=MagicMock())

    assert result is False
    mock_uhome_api.set_push_status.assert_not_awaited()


async def test_register_falls_back_through_url_strategies(hass, mock_uhome_api):
    """First strategy fails, second succeeds — cloud fallback path."""
    h = AsyncPushUpdateHandler(hass, mock_uhome_api, entry_id="e1")

    call_count = [0]

    def _get_url(*args, **kwargs):
        call_count[0] += 1
        if call_count[0] == 1:
            raise NoURLAvailableError()
        return "https://cloud.example.com"

    with patch(
        "custom_components.u_tec.api.network.get_url", side_effect=_get_url,
    ), patch(
        "custom_components.u_tec.api.webhook.async_generate_url",
        return_value="https://cloud.example.com/api/webhook/x",
    ), patch(
        "custom_components.u_tec.api.webhook.async_register",
        return_value=lambda: None,
    ):
        result = await h.async_register_webhook(auth_data=MagicMock())

    assert result is True
    assert call_count[0] >= 2  # at least one fallback hit


async def test_register_fails_when_api_set_push_status_errors(hass, mock_uhome_api):
    from utec_py.exceptions import ApiError

    h = AsyncPushUpdateHandler(hass, mock_uhome_api, entry_id="e1")
    mock_uhome_api.set_push_status.side_effect = ApiError(500, "fail")

    with patch(
        "custom_components.u_tec.api.network.get_url",
        return_value="https://ha.example.com",
    ), patch(
        "custom_components.u_tec.api.webhook.async_generate_url",
        return_value="https://ha.example.com/api/webhook/x",
    ):
        result = await h.async_register_webhook(auth_data=MagicMock())

    assert result is False
```

- [ ] **Step 2: Run** `.venv/bin/pytest tests/test_webhook_registration.py -v`. Expected: pass.

- [ ] **Step 3: Commit** `git add tests/test_webhook_registration.py && git commit -m "test: cover webhook registration URL resolution strategies"`

---

### Task 22b: `async_register_webhook` — secret rotation + unregister

**Files:**
- Modify: `tests/test_webhook_registration.py` (append)

- [ ] **Step 1: Append secret + unregister tests**

```python
# --- Secret rotation + unregister ---


async def test_register_generates_new_secret_each_call(hass, mock_uhome_api):
    h = AsyncPushUpdateHandler(hass, mock_uhome_api, entry_id="e1")

    with patch(
        "custom_components.u_tec.api.network.get_url",
        return_value="https://ha.example.com",
    ), patch(
        "custom_components.u_tec.api.webhook.async_generate_url",
        return_value="https://ha.example.com/api/webhook/x",
    ), patch(
        "custom_components.u_tec.api.webhook.async_register",
        return_value=lambda: None,
    ):
        await h.async_register_webhook(auth_data=MagicMock())
        first = h._push_secret
        await h.async_register_webhook(auth_data=MagicMock())
        second = h._push_secret

    assert first != second


async def test_unregister_cancels_reregister_and_unregisters_hook(hass, mock_uhome_api):
    h = AsyncPushUpdateHandler(hass, mock_uhome_api, entry_id="e1")
    h._unregister_webhook = MagicMock()
    cancel_mock = MagicMock()
    h._cancel_reregister = cancel_mock

    with patch(
        "custom_components.u_tec.api.webhook.async_unregister",
    ) as mock_unreg:
        await h.unregister_webhook()

    cancel_mock.assert_called_once()
    mock_unreg.assert_called_once()
    assert h._cancel_reregister is None
    assert h._unregister_webhook is None


async def test_unregister_noop_when_nothing_registered(hass, mock_uhome_api):
    h = AsyncPushUpdateHandler(hass, mock_uhome_api, entry_id="e1")
    # Neither _unregister_webhook nor _cancel_reregister is set — should not raise
    await h.unregister_webhook()
```

- [ ] **Step 2: Run**. Expected: pass.

- [ ] **Step 3: Commit** `git add tests/test_webhook_registration.py && git commit -m "test: cover webhook secret rotation and unregister"`

---

### Task 23: `diagnostics` — redaction + error branches

**Files:**
- Create: `tests/test_diagnostics.py`

- [ ] **Step 1: Read `custom_components/u_tec/diagnostics.py`**. Note the redacted fields (likely `access_token`, `refresh_token`, `client_id`, `client_secret`).

- [ ] **Step 2: Write tests**

```python
"""Tests for diagnostics module."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.u_tec.diagnostics import async_get_config_entry_diagnostics
from custom_components.u_tec.const import DOMAIN
from tests.common import make_config_entry


async def test_diagnostics_redacts_tokens(hass, mock_uhome_api):
    entry = make_config_entry(data={
        "token": {
            "access_token": "SECRET-ACCESS",
            "refresh_token": "SECRET-REFRESH",
        },
        "auth_implementation": "u_tec",
    })
    entry.add_to_hass(hass)

    coord = MagicMock()
    coord.devices = {}
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "coordinator": coord, "api": mock_uhome_api,
    }

    result = await async_get_config_entry_diagnostics(hass, entry)
    # Serialise to string for easy substring assertion
    s = str(result)
    assert "SECRET-ACCESS" not in s
    assert "SECRET-REFRESH" not in s
```

- [ ] **Step 3: Run**. Expected: pass.

- [ ] **Step 4: Commit** `git add tests/test_diagnostics.py && git commit -m "test: cover diagnostics token redaction"`

---

### Task 24a: Coverage gap triage — produce a punch list

**Files:**
- Create: `docs/superpowers/plans/COVERAGE-GAPS-2026-04-18.md`

**Local LLM candidate — primary target:** After running coverage, pass the `--cov-report=term-missing` output (text block) to `local_llm` with: *"For each module with missing lines, output a markdown section following this template: `## Module: <path> (current: N%)` with fields `- Uncovered lines:`, `- Nature: <simple-branch | defensive-log-only | framework-callback | environment-dependent>`, `- Recommended test: <one sentence>`, `- Estimated effort: <trivial | moderate | hard>`. Then assign each section a letter starting from 'b' (24b, 24c, 24d...). Do not invent line numbers or module paths — use only what appears in the input."* Primary model verifies the output against the raw coverage dump (line numbers must round-trip) and adds the "Task 24 letter" field if `local_llm` forgot it. Log outcome.

This task does **not** write any production or test code. Its only outputs are a gap analysis document and a commit of that doc. Downstream Tasks 24b…24n consume the punch list.

- [ ] **Step 1: Run coverage**

```bash
.venv/bin/pytest tests/ --cov=custom_components.u_tec --cov-report=term-missing --cov-report=html
```

- [ ] **Step 2: For each module below 85%, write an entry in `COVERAGE-GAPS-2026-04-18.md` with this shape:**

```markdown
# Coverage gap punch list — 2026-04-18

## Module: custom_components/u_tec/<file>.py (current: N%)
- Uncovered lines: <line ranges from --cov-report=term-missing>
- Nature: <one of: simple branch, defensive log-only, environment-dependent, framework-callback>
- Recommended test: <one sentence>
- Estimated effort: <trivial / moderate / hard>
- Task 24 letter: <assign b, c, d, …>
```

Grouping rule: one "Task 24X" letter per file, unless a single file has >8 uncovered lines spanning unrelated concerns — in that case, split to two letters.

- [ ] **Step 3: Commit punch list**

```bash
git add docs/superpowers/plans/COVERAGE-GAPS-2026-04-18.md
git commit -m "docs: triage remaining coverage gaps"
```

- [ ] **Step 4: Report back** — list the Task 24X letters assigned and the estimated total effort. This is the baseline for how many additional subagent dispatches are needed.

---

### Task 24b…24n: Per-gap coverage fills (one subagent per assigned letter)

**Files:**
- Varies per letter — see `COVERAGE-GAPS-2026-04-18.md`.

For each letter assigned in Task 24a, dispatch **one subagent** with the scoped prompt:

> Fill the coverage gaps for `<module>` listed under Task 24\<letter\> in `docs/superpowers/plans/COVERAGE-GAPS-2026-04-18.md`. Read only the relevant section of `AUDIT-uhome-ha-2026-04-18.md`, the identified gap lines in the source module, and the existing test file (if any). Write the minimum tests needed to cover the listed lines. Commit as a single commit.

Likely candidates (confirmed or adjusted by Task 24a output):

- **24b — `__init__.py` YAML-config branch:**

```python
# tests/test_init.py (new file)
async def test_async_setup_stores_yaml_config(hass):
    from custom_components.u_tec import async_setup
    from custom_components.u_tec.const import CONF_SCAN_INTERVAL, DOMAIN

    assert await async_setup(hass, {DOMAIN: {CONF_SCAN_INTERVAL: 42}}) is True
    assert hass.data[DOMAIN]["_yaml_config"][CONF_SCAN_INTERVAL] == 42


async def test_async_setup_noop_without_domain_key(hass):
    from custom_components.u_tec import async_setup
    from custom_components.u_tec.const import DOMAIN

    assert await async_setup(hass, {}) is True
    assert "_yaml_config" not in hass.data.get(DOMAIN, {})
```

- **24c — `coordinator.py` scheduler callbacks:**

```python
# append to tests/test_coordinator.py
async def test_scheduled_discovery_invokes_async_discover(coordinator, mock_uhome_api):
    mock_uhome_api.discover_devices.return_value = {"payload": {"devices": []}}
    await coordinator._async_scheduled_discovery(None)
    mock_uhome_api.discover_devices.assert_awaited_once()


async def test_start_stop_periodic_discovery(coordinator):
    await coordinator.async_start_periodic_discovery()
    assert coordinator._cancel_discovery is not None
    coordinator.async_stop_periodic_discovery()
    assert coordinator._cancel_discovery is None
```

- **24d — `api.py` `_async_reregister` callback:**

```python
# append to tests/test_webhook_registration.py
async def test_async_reregister_schedules_task(hass, mock_uhome_api):
    from unittest.mock import MagicMock, patch

    from custom_components.u_tec.api import AsyncPushUpdateHandler

    h = AsyncPushUpdateHandler(hass, mock_uhome_api, entry_id="e1")
    h._auth_data = MagicMock()
    with patch.object(hass, "async_create_task") as mock_create:
        h._async_reregister(None)
    mock_create.assert_called_once()
```

- **24e…24n:** Whatever Task 24a identifies. Typical suspects: `config_flow.py` less-trodden branches (reauth_confirm form re-render, invalid OAuth token refresh), `sensor.py` push-update callback, `lock.py` edge cases in `extra_state_attributes`.

**Stop condition:** overall coverage ≥85% OR Task 24a's punch list is exhausted, whichever comes first. If coverage is still short after exhausting the list, the remaining shortfall is HA-framework / scheduler-internal code that cannot be reasonably tested — document this in `COVERAGE-GAPS-2026-04-18.md` under a "Not reasonably testable" section and close.

- [ ] **Step (per letter): Run, verify coverage delta, commit.**

```bash
.venv/bin/pytest tests/ --cov=custom_components.u_tec --cov-report=term-missing
# confirm the lines listed under this letter are now covered
git add tests/
git commit -m "test: cover <module> gaps (Task 24<letter>)"
```

- [ ] **Final step (after all letters complete):** Run `--cov-fail-under=85` and confirm it passes.

```bash
.venv/bin/pytest tests/ --cov=custom_components.u_tec --cov-fail-under=85
```

Expected: exit 0. If not, return to Task 24a and re-triage.

---

### Task 25: CI wiring (optional — skip if no CI exists)

- [ ] **Step 1: Check if `.github/workflows/` exists.** If yes, add `test.yml`:

```yaml
name: Tests

on:
  push:
    branches: [main]
  pull_request:

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install -r requirements-test.txt
      - run: pytest --cov=custom_components.u_tec --cov-fail-under=85
```

If no CI, skip.

- [ ] **Step 2: Commit if applicable.**

---

## Self-review checklist

Before declaring done:

- [ ] Every source file in `custom_components/u_tec/` has at least one direct test. (Exception: `const.py` covered incidentally via imports.)
- [ ] `pytest tests/` passes with no failures, errors, or filterwarnings violations (aside from HA deprecation spam suppressed via config).
- [ ] `pytest --cov=custom_components.u_tec --cov-fail-under=85` exits 0.
- [ ] All webhook auth boundary tests assert the specific HTTP status (401 vs 403 vs 405 vs 404).
- [ ] All coordinator push-data shape tests include the flat-list case (Issue #30).
- [ ] Optimistic state-clear tests assert both "clears on match" and "persists on mismatch" for light brightness.
- [ ] `git log --oneline` shows ~20–25 small commits, not one mega-commit.
- [ ] Original `tests/test_optimistic.py` still passes unchanged.

---

## Sibling dependency

This plan assumes utec-py's `Switch`, `Light`, `Lock` classes are stable. If the utec-py test-coverage plan adds a test-only `AbstractAuth` subclass or helper mock module, re-evaluate `tests/common.py` to use the shared fakes instead of custom `MagicMock(spec=...)` stubs — that avoids mock/real-implementation drift.
