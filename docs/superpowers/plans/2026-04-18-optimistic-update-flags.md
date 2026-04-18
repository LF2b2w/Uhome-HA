# Optimistic-Update Flags Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add per-device-type optimistic-update configuration flags (lights / switches / locks) with three modes each — all devices, no devices, or a picked subset — exposed via the existing options flow UI. Default behavior is unchanged (always-optimistic) for backwards compatibility.

**Architecture:** Resolver function reads `entry.options` to determine whether each device should apply optimistic updates. Light, switch, and lock entities gate their `_optimistic_*` writes and expose `assumed_state` behind that resolver. Options flow gains a new menu step with a mode selector per type and conditional multi-select pickers.

**Tech Stack:** Python 3.12, Home Assistant `custom_component`, voluptuous, pytest.

**Spec:** [`docs/superpowers/specs/2026-04-18-optimistic-update-flags-design.md`](../specs/2026-04-18-optimistic-update-flags-design.md)

---

## File Structure

**New files:**
- `custom_components/u_tec/optimistic.py` — resolver + new constants. Deliberately has zero project imports so it is unit-testable without loading Home Assistant.
- `tests/__init__.py` — empty marker so pytest treats `tests/` as a package.
- `tests/conftest.py` — adds `custom_components/u_tec/` to `sys.path` so the standalone `optimistic.py` module can be imported directly.
- `tests/test_optimistic.py` — unit tests for the resolver.
- `pytest.ini` — pytest configuration.
- `requirements-test.txt` — pytest dependency.

**Modified files:**
- `custom_components/u_tec/const.py` — re-export constants from `optimistic.py`.
- `custom_components/u_tec/coordinator.py` — accept and store `config_entry`.
- `custom_components/u_tec/__init__.py` — pass `entry` to coordinator.
- `custom_components/u_tec/switch.py` — gate optimistic writes, add `assumed_state`.
- `custom_components/u_tec/light.py` — gate optimistic writes, add `assumed_state`.
- `custom_components/u_tec/lock.py` — gate optimistic writes, add `assumed_state`.
- `custom_components/u_tec/config_flow.py` — new menu item, mode step, three picker steps.
- `custom_components/u_tec/strings.json` — labels for new steps (and matching translation files if they exist under `translations/`).

---

## Task 1: Test scaffolding + resolver (TDD)

**Files:**
- Create: `pytest.ini`
- Create: `requirements-test.txt`
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`
- Create: `tests/test_optimistic.py`
- Create: `custom_components/u_tec/optimistic.py`
- Modify: `custom_components/u_tec/const.py`

### Step 1: Create `pytest.ini`

- [ ] **Step 1: Create pytest config**

```ini
[pytest]
testpaths = tests
addopts = -q
```

### Step 2: Create `requirements-test.txt`

- [ ] **Step 2: Create test requirements**

```
pytest>=7
```

### Step 3: Create `tests/__init__.py` and `tests/conftest.py`

- [ ] **Step 3a: Create `tests/__init__.py`** (empty file)

```python
```

- [ ] **Step 3b: Create `tests/conftest.py`**

```python
"""Pytest setup for standalone u_tec tests.

The resolver lives in `custom_components/u_tec/optimistic.py` and has
no Home Assistant imports. Adding that directory to `sys.path` lets tests
import it as a top-level module without triggering the package's
`__init__.py` (which pulls in Home Assistant).
"""

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "custom_components" / "u_tec"))
```

### Step 4: Write the failing tests

- [ ] **Step 4: Create `tests/test_optimistic.py`**

```python
"""Unit tests for the optimistic-update resolver."""

from optimistic import (
    CONF_OPTIMISTIC_LIGHTS,
    DEFAULT_OPTIMISTIC,
    is_optimistic_enabled,
)


def test_default_constant_is_true():
    assert DEFAULT_OPTIMISTIC is True


def test_missing_key_returns_default_true():
    assert is_optimistic_enabled({}, CONF_OPTIMISTIC_LIGHTS, "dev-1") is True


def test_true_value_returns_true():
    options = {CONF_OPTIMISTIC_LIGHTS: True}
    assert is_optimistic_enabled(options, CONF_OPTIMISTIC_LIGHTS, "dev-1") is True


def test_false_value_returns_false():
    options = {CONF_OPTIMISTIC_LIGHTS: False}
    assert is_optimistic_enabled(options, CONF_OPTIMISTIC_LIGHTS, "dev-1") is False


def test_list_with_match_returns_true():
    options = {CONF_OPTIMISTIC_LIGHTS: ["dev-1", "dev-2"]}
    assert is_optimistic_enabled(options, CONF_OPTIMISTIC_LIGHTS, "dev-1") is True


def test_list_without_match_returns_false():
    options = {CONF_OPTIMISTIC_LIGHTS: ["dev-2"]}
    assert is_optimistic_enabled(options, CONF_OPTIMISTIC_LIGHTS, "dev-1") is False


def test_empty_list_returns_false():
    options = {CONF_OPTIMISTIC_LIGHTS: []}
    assert is_optimistic_enabled(options, CONF_OPTIMISTIC_LIGHTS, "dev-1") is False


def test_different_keys_resolve_independently():
    options = {
        "optimistic_lights": True,
        "optimistic_switches": False,
    }
    assert is_optimistic_enabled(options, "optimistic_lights", "dev-1") is True
    assert is_optimistic_enabled(options, "optimistic_switches", "dev-1") is False
```

### Step 5: Run tests to verify they fail

- [ ] **Step 5: Run pytest — expect ImportError**

```bash
cd /Users/gfranks/workspace/Uhome-HA
python3 -m venv .venv
.venv/bin/pip install -r requirements-test.txt
.venv/bin/pytest
```

Expected: collection error — `ModuleNotFoundError: No module named 'optimistic'`.

### Step 6: Create the resolver module

- [ ] **Step 6: Create `custom_components/u_tec/optimistic.py`**

```python
"""Optimistic-update configuration resolver.

Standalone module with no project or Home Assistant imports, so it can be
unit-tested without loading the integration package or Home Assistant.
"""

from __future__ import annotations

from typing import Any, Mapping

CONF_OPTIMISTIC_LIGHTS = "optimistic_lights"
CONF_OPTIMISTIC_SWITCHES = "optimistic_switches"
CONF_OPTIMISTIC_LOCKS = "optimistic_locks"
DEFAULT_OPTIMISTIC = True


def is_optimistic_enabled(
    options: Mapping[str, Any],
    conf_key: str,
    device_id: str,
) -> bool:
    """Return True if optimistic updates are enabled for this device.

    value shape:
      - absent  -> DEFAULT_OPTIMISTIC (True)
      - True    -> all devices of this type optimistic
      - False   -> no devices of this type optimistic
      - list    -> only listed device IDs optimistic
    """
    value = options.get(conf_key, DEFAULT_OPTIMISTIC)
    if isinstance(value, bool):
        return value
    return device_id in value
```

### Step 7: Re-export from `const.py`

- [ ] **Step 7: Add re-exports to `custom_components/u_tec/const.py`**

Append these lines to `const.py` (after the existing constants):

```python
from .optimistic import (  # noqa: E402 (re-export for package consumers)
    CONF_OPTIMISTIC_LIGHTS,
    CONF_OPTIMISTIC_SWITCHES,
    CONF_OPTIMISTIC_LOCKS,
    DEFAULT_OPTIMISTIC,
    is_optimistic_enabled,
)
```

### Step 8: Run tests to verify they pass

- [ ] **Step 8: Run pytest**

```bash
.venv/bin/pytest
```

Expected: 8 passed.

### Step 9: Commit

- [ ] **Step 9: Commit**

```bash
git add pytest.ini requirements-test.txt tests/ custom_components/u_tec/optimistic.py custom_components/u_tec/const.py
git commit -m "Add optimistic-update resolver and test harness"
```

---

## Task 2: Store config entry on coordinator

Entities need a live handle to `entry.options` so they pick up runtime changes (options-flow saves trigger `async_reload`, which rebuilds entities; each new entity then reads current options at runtime). The coordinator is the natural place to hold the entry — entities already hold a reference to the coordinator.

**Files:**
- Modify: `custom_components/u_tec/coordinator.py:22-48`
- Modify: `custom_components/u_tec/__init__.py:90-95`

No automated tests — verified by restarting the integration and observing clean load in the Home Assistant log.

### Step 1: Add `config_entry` parameter to coordinator

- [ ] **Step 1: Modify `UhomeDataUpdateCoordinator.__init__`**

Change the constructor signature + body in `custom_components/u_tec/coordinator.py`:

```python
from homeassistant.config_entries import ConfigEntry

# ...

class UhomeDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching Uhome data."""

    def __init__(
        self,
        hass: HomeAssistant,
        api: UHomeApi,
        config_entry: ConfigEntry,
        scan_interval: int = DEFAULT_SCAN_INTERVAL,
        discovery_interval: int = DEFAULT_DISCOVERY_INTERVAL,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name="Uhome devices",
            update_interval=timedelta(seconds=scan_interval),
        )
        self.api = api
        self.config_entry = config_entry
        self.devices: dict[str, BaseDevice] = {}
        self.added_sensor_entities = set()
        self.push_devices = []
        self.blacklisted_devices = []
        self._discovery_interval = timedelta(seconds=discovery_interval)
        self._cancel_discovery: callable | None = None
        _LOGGER.info(
            "Uhome data coordinator initialized (poll=%ds, discovery=%ds)",
            scan_interval,
            discovery_interval,
        )
```

### Step 2: Pass `entry` when constructing the coordinator

- [ ] **Step 2: Modify `async_setup_entry` in `__init__.py`**

Replace the `UhomeDataUpdateCoordinator(...)` call with:

```python
    coordinator = UhomeDataUpdateCoordinator(
        hass,
        Uhomeapi,
        config_entry=entry,
        scan_interval=scan_interval,
        discovery_interval=discovery_interval,
    )
```

### Step 3: Manual verification

- [ ] **Step 3: Restart Home Assistant and confirm clean integration load**

Look for `"Uhome data coordinator initialized"` in the HA log, with no stack traces referring to `config_entry`.

### Step 4: Commit

- [ ] **Step 4: Commit**

```bash
git add custom_components/u_tec/coordinator.py custom_components/u_tec/__init__.py
git commit -m "Store config entry on coordinator for entity access to options"
```

---

## Task 3: Gate optimistic updates in switch.py

Simplest entity (single optimistic field). Establishes the pattern reused in Tasks 4–5.

**Files:**
- Modify: `custom_components/u_tec/switch.py`

No automated tests. Manual verification at the end of the task.

### Step 1: Add imports

- [ ] **Step 1: Update imports in `switch.py`**

Change the `from .const import` line to:

```python
from .const import (
    CONF_OPTIMISTIC_SWITCHES,
    DOMAIN,
    SIGNAL_DEVICE_UPDATE,
    is_optimistic_enabled,
)
```

### Step 2: Add `_is_optimistic` helper on the entity

- [ ] **Step 2: Add helper method**

Inside `UhomeSwitchEntity`, right below `__init__`, add:

```python
def _is_optimistic(self) -> bool:
    """Return True if optimistic updates apply to this device."""
    return is_optimistic_enabled(
        self.coordinator.config_entry.options,
        CONF_OPTIMISTIC_SWITCHES,
        self._device.device_id,
    )
```

### Step 3: Add `assumed_state` property

- [ ] **Step 3: Add property**

Add right below `is_on` property:

```python
@property
def assumed_state(self) -> bool:
    """Return True if the current state is optimistic rather than confirmed."""
    return self._is_optimistic()
```

### Step 4: Gate `async_turn_on`

- [ ] **Step 4: Replace `async_turn_on` body**

Replace the existing method with:

```python
    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the switch on."""
        _LOGGER.debug("Turning on switch %s", self._device.device_id)
        try:
            await self._device.turn_on()
            if self._is_optimistic():
                self._optimistic_is_on = True
                self.async_write_ha_state()
        except DeviceError as err:
            _LOGGER.error(
                "Failed to turn on switch %s: %s", self._device.device_id, err
            )
            raise HomeAssistantError(f"Failed to turn on switch: {err}") from err
```

### Step 5: Gate `async_turn_off`

- [ ] **Step 5: Replace `async_turn_off` body**

```python
    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the switch off."""
        _LOGGER.debug("Turning off switch %s", self._device.device_id)
        try:
            await self._device.turn_off()
            if self._is_optimistic():
                self._optimistic_is_on = False
                self.async_write_ha_state()
        except DeviceError as err:
            _LOGGER.error(
                "Failed to turn off switch %s: %s", self._device.device_id, err
            )
            raise HomeAssistantError(f"Failed to turn off switch: {err}") from err
```

### Step 6: Manual verification

- [ ] **Step 6: Verify in HA**

1. Restart Home Assistant.
2. Confirm any switch entity is still responsive to on/off commands.
3. In the UI, the "assumed" badge should appear (options key absent → default True).

### Step 7: Commit

- [ ] **Step 7: Commit**

```bash
git add custom_components/u_tec/switch.py
git commit -m "Gate switch optimistic updates and assumed_state behind resolver"
```

---

## Task 4: Gate optimistic updates in light.py

Same pattern as switch, but a single lights flag gates both `_optimistic_is_on` and `_optimistic_brightness` (plus `_pending_brightness_utec`).

**Files:**
- Modify: `custom_components/u_tec/light.py`

### Step 1: Update imports

- [ ] **Step 1: Update imports in `light.py`**

Change the `from .const import` line to:

```python
from .const import (
    CONF_OPTIMISTIC_LIGHTS,
    DOMAIN,
    SIGNAL_DEVICE_UPDATE,
    is_optimistic_enabled,
)
```

### Step 2: Add `_is_optimistic` helper

- [ ] **Step 2: Add helper method on `UhomeLightEntity`**

Add right below `__init__`:

```python
def _is_optimistic(self) -> bool:
    """Return True if optimistic updates apply to this device."""
    return is_optimistic_enabled(
        self.coordinator.config_entry.options,
        CONF_OPTIMISTIC_LIGHTS,
        self._device.device_id,
    )
```

### Step 3: Add `assumed_state` property

- [ ] **Step 3: Add property**

Add right below `brightness` property:

```python
@property
def assumed_state(self) -> bool:
    """Return True if the current state is optimistic rather than confirmed."""
    return self._is_optimistic()
```

### Step 4: Gate `async_turn_on`

- [ ] **Step 4: Replace `async_turn_on` body**

```python
    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the light on."""
        _LOGGER.debug("Turning on light %s kwargs=%s", self._device.device_id, kwargs)
        try:
            turn_on_args = {}

            if ATTR_BRIGHTNESS in kwargs:
                brightness_255 = kwargs[ATTR_BRIGHTNESS]
                utec_brightness = max(1, int((brightness_255 / 255) * 100))
                turn_on_args["brightness"] = utec_brightness

            if ATTR_RGB_COLOR in kwargs:
                turn_on_args["rgb_color"] = kwargs[ATTR_RGB_COLOR]

            if ATTR_COLOR_TEMP_KELVIN in kwargs:
                turn_on_args["color_temp"] = kwargs[ATTR_COLOR_TEMP_KELVIN]

            await self._device.turn_on(**turn_on_args)

            if self._is_optimistic():
                self._optimistic_is_on = True
                if "brightness" in turn_on_args:
                    self._optimistic_brightness = kwargs[ATTR_BRIGHTNESS]
                    self._pending_brightness_utec = turn_on_args["brightness"]
                self.async_write_ha_state()

        except DeviceError as err:
            _LOGGER.error("Failed to turn on light %s: %s", self._device.device_id, err)
            raise HomeAssistantError(f"Failed to turn on light: {err}") from err
```

### Step 5: Gate `async_turn_off`

- [ ] **Step 5: Replace `async_turn_off` body**

```python
    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the light off."""
        _LOGGER.debug("Turning off light %s", self._device.device_id)
        try:
            await self._device.turn_off()
            if self._is_optimistic():
                self._optimistic_is_on = False
                self.async_write_ha_state()
        except DeviceError as err:
            _LOGGER.error(
                "Failed to turn off light %s: %s", self._device.device_id, err
            )
            raise HomeAssistantError(f"Failed to turn off light: {err}") from err
```

### Step 6: Manual verification

- [ ] **Step 6: Verify in HA**

1. Restart Home Assistant.
2. Toggle any light entity (on/off and brightness slider).
3. With options absent, behavior should be identical to pre-change.

### Step 7: Commit

- [ ] **Step 7: Commit**

```bash
git add custom_components/u_tec/light.py
git commit -m "Gate light optimistic updates and assumed_state behind resolver"
```

---

## Task 5: Gate optimistic updates in lock.py

**Files:**
- Modify: `custom_components/u_tec/lock.py`

### Step 1: Update imports

- [ ] **Step 1: Update imports in `lock.py`**

```python
from .const import (
    CONF_OPTIMISTIC_LOCKS,
    DOMAIN,
    SIGNAL_DEVICE_UPDATE,
    is_optimistic_enabled,
)
```

### Step 2: Add `_is_optimistic` helper

- [ ] **Step 2: Add helper method on `UhomeLockEntity`**

Add right below `__init__`:

```python
def _is_optimistic(self) -> bool:
    """Return True if optimistic updates apply to this device."""
    return is_optimistic_enabled(
        self.coordinator.config_entry.options,
        CONF_OPTIMISTIC_LOCKS,
        self._device.device_id,
    )
```

### Step 3: Add `assumed_state` property

- [ ] **Step 3: Add property**

Add right below `is_jammed` property:

```python
@property
def assumed_state(self) -> bool:
    """Return True if the current state is optimistic rather than confirmed."""
    return self._is_optimistic()
```

### Step 4: Gate `async_lock`

- [ ] **Step 4: Replace `async_lock` body**

```python
    async def async_lock(self, **kwargs: Any) -> None:
        """Lock the device."""
        _LOGGER.debug("Locking device %s", self._device.device_id)
        try:
            await self._device.lock()
            if self._is_optimistic():
                self._optimistic_is_locked = True
                self.async_write_ha_state()
        except DeviceError as err:
            _LOGGER.error("Failed to lock device %s: %s", self._device.device_id, err)
            raise HomeAssistantError(f"Failed to lock: {err}") from err
```

### Step 5: Gate `async_unlock`

- [ ] **Step 5: Replace `async_unlock` body**

```python
    async def async_unlock(self, **kwargs: Any) -> None:
        """Unlock the device."""
        _LOGGER.debug("Unlocking device %s", self._device.device_id)
        try:
            await self._device.unlock()
            if self._is_optimistic():
                self._optimistic_is_locked = False
                self.async_write_ha_state()
        except DeviceError as err:
            _LOGGER.error("Failed to unlock device %s: %s", self._device.device_id, err)
            raise HomeAssistantError(f"Failed to unlock: {err}") from err
```

### Step 6: Manual verification

- [ ] **Step 6: Verify in HA**

1. Restart Home Assistant.
2. Trigger lock/unlock from UI; confirm entity responds normally.

### Step 7: Commit

- [ ] **Step 7: Commit**

```bash
git add custom_components/u_tec/lock.py
git commit -m "Gate lock optimistic updates and assumed_state behind resolver"
```

---

## Task 6: Options flow — menu entry + mode step

Adds the first new options-flow screen. If no device-type is set to `custom`, this screen finalizes the entry immediately. Task 7 adds the conditional picker steps.

**Files:**
- Modify: `custom_components/u_tec/config_flow.py`
- Modify: `custom_components/u_tec/strings.json`

No automated tests. Manual verification via the HA UI.

### Step 1: Add imports and mode constants

- [ ] **Step 1: Update imports at top of `config_flow.py`**

Add these to the existing `from homeassistant.helpers.selector import` line (and adjust import list):

```python
from homeassistant.helpers.selector import (
    BooleanSelector,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)
```

Add to the `from .const import` block:

```python
from .const import (
    CONF_API_SCOPE,
    CONF_HA_DEVICES,
    CONF_OPTIMISTIC_LIGHTS,
    CONF_OPTIMISTIC_LOCKS,
    CONF_OPTIMISTIC_SWITCHES,
    CONF_PUSH_DEVICES,
    CONF_PUSH_ENABLED,
    DEFAULT_API_SCOPE,
    DOMAIN,
)
```

Add these module-level helpers below the existing `STEP_USER_DATA_SCHEMA`:

```python
OPTIMISTIC_MODE_ALL = "all"
OPTIMISTIC_MODE_NONE = "none"
OPTIMISTIC_MODE_CUSTOM = "custom"
OPTIMISTIC_MODES = [OPTIMISTIC_MODE_ALL, OPTIMISTIC_MODE_NONE, OPTIMISTIC_MODE_CUSTOM]


def _current_mode(value):
    """Infer the mode selector default from a stored option value."""
    if value is True or value is None:
        return OPTIMISTIC_MODE_ALL
    if value is False:
        return OPTIMISTIC_MODE_NONE
    return OPTIMISTIC_MODE_CUSTOM
```

### Step 2: Add menu entry

- [ ] **Step 2: Update `async_step_init` in `OptionsFlowHandler`**

Replace the `menu_options` block with:

```python
        return self.async_show_menu(
            step_id="init",
            menu_options={
                "update_push": "Update Push Status",
                "get_devices": "Select Active Devices",
                "optimistic_updates": "Configure Optimistic Updates",
            },
        )
```

### Step 3: Add instance state for picker chain

- [ ] **Step 3: Initialize `_pending_pickers` in `__init__`**

Modify `OptionsFlowHandler.__init__` to add the new attribute:

```python
    def __init__(self, config_entry: ConfigEntry) -> None:
        """Initialise OptionsFlowHandler."""
        super().__init__()
        self.api = None
        self.devices = {}
        self.options = dict(config_entry.options)
        self._pending_pickers: list[str] = []
```

### Step 4: Add `async_step_optimistic_updates`

- [ ] **Step 4: Add the mode-selection step**

Add this method inside `OptionsFlowHandler`, immediately after `async_step_push_device_selection`:

```python
    async def async_step_optimistic_updates(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Configure optimistic updates per device type."""
        mode_selector = SelectSelector(
            SelectSelectorConfig(
                options=OPTIMISTIC_MODES,
                mode=SelectSelectorMode.DROPDOWN,
                translation_key="optimistic_mode",
            )
        )

        if user_input is not None:
            self._pending_pickers = []
            for conf_key, field in (
                (CONF_OPTIMISTIC_LIGHTS, "lights_mode"),
                (CONF_OPTIMISTIC_SWITCHES, "switches_mode"),
                (CONF_OPTIMISTIC_LOCKS, "locks_mode"),
            ):
                mode = user_input[field]
                if mode == OPTIMISTIC_MODE_ALL:
                    self.options[conf_key] = True
                elif mode == OPTIMISTIC_MODE_NONE:
                    self.options[conf_key] = False
                elif mode == OPTIMISTIC_MODE_CUSTOM:
                    self._pending_pickers.append(conf_key)
            return await self._advance_optimistic_picker()

        lights_default = _current_mode(self.options.get(CONF_OPTIMISTIC_LIGHTS))
        switches_default = _current_mode(self.options.get(CONF_OPTIMISTIC_SWITCHES))
        locks_default = _current_mode(self.options.get(CONF_OPTIMISTIC_LOCKS))

        return self.async_show_form(
            step_id="optimistic_updates",
            data_schema=vol.Schema(
                {
                    vol.Required("lights_mode", default=lights_default): mode_selector,
                    vol.Required("switches_mode", default=switches_default): mode_selector,
                    vol.Required("locks_mode", default=locks_default): mode_selector,
                }
            ),
        )

    async def _advance_optimistic_picker(self) -> ConfigFlowResult:
        """Dispatch to the next pending picker, or finalise."""
        if not self._pending_pickers:
            return self.async_create_entry(title="", data=self.options)
        # Picker step names are added in Task 7. For this task, finalise
        # regardless — falling through to create_entry keeps the mode step
        # functional before Task 7 lands.
        return self.async_create_entry(title="", data=self.options)
```

### Step 5: Update `strings.json`

- [ ] **Step 5: Add translation keys**

Inside the existing `options.step` object in `custom_components/u_tec/strings.json`, add a new `optimistic_updates` entry:

```json
"optimistic_updates": {
  "title": "Optimistic Updates",
  "description": "Pick how each device type should reflect commands. 'All' writes optimistic state for every device of that type, 'None' waits for confirmed state, 'Custom' lets you pick specific devices.",
  "data": {
    "lights_mode": "Lights",
    "switches_mode": "Switches",
    "locks_mode": "Locks"
  }
}
```

Also add (sibling of `options`, i.e. top-level `selector`) translation-key labels for the mode dropdown:

```json
"selector": {
  "optimistic_mode": {
    "options": {
      "all": "All devices optimistic",
      "none": "No devices optimistic",
      "custom": "Custom per-device"
    }
  }
}
```

If the project already has a `selector` key, merge rather than overwrite. If additional files exist under `custom_components/u_tec/translations/` (e.g. `en.json`), mirror these additions there too.

### Step 6: Manual verification

- [ ] **Step 6: Verify the new menu flow in HA**

1. Restart Home Assistant.
2. Integrations → Uhome → Configure.
3. "Configure Optimistic Updates" should appear in the menu.
4. Pick it; the mode form should render with three dropdowns defaulting to `All`.
5. Submit with all three = `All` → form closes, no errors in the log.
6. Re-open; values should persist (`entry.options` shows `optimistic_lights: True`, etc.).
7. Re-open and set all three to `None` → submit → verify entry options reflect `False`.

### Step 7: Commit

- [ ] **Step 7: Commit**

```bash
git add custom_components/u_tec/config_flow.py custom_components/u_tec/strings.json
git commit -m "Add optimistic-updates mode step to options flow"
```

---

## Task 7: Options flow — per-type picker steps

Replace the stub branch in `_advance_optimistic_picker` with a real chain that shows a device picker for each type set to `custom`.

**Files:**
- Modify: `custom_components/u_tec/config_flow.py`
- Modify: `custom_components/u_tec/strings.json`

### Step 1: Import device-type classes

- [ ] **Step 1: Add utec_py device imports**

At the top of `config_flow.py`:

```python
from utec_py.devices.light import Light as UhomeLight
from utec_py.devices.lock import Lock as UhomeLock
from utec_py.devices.switch import Switch as UhomeSwitch
```

### Step 2: Replace `_advance_optimistic_picker`

- [ ] **Step 2: Replace the stub with real dispatch**

```python
    async def _advance_optimistic_picker(self) -> ConfigFlowResult:
        """Dispatch to the next pending picker, or finalise."""
        if not self._pending_pickers:
            return self.async_create_entry(title="", data=self.options)
        next_key = self._pending_pickers[0]
        dispatch = {
            CONF_OPTIMISTIC_LIGHTS: self.async_step_pick_lights,
            CONF_OPTIMISTIC_SWITCHES: self.async_step_pick_switches,
            CONF_OPTIMISTIC_LOCKS: self.async_step_pick_locks,
        }
        return await dispatch[next_key]()
```

### Step 3: Add a shared picker helper

- [ ] **Step 3: Add `_optimistic_picker_step`**

```python
    async def _optimistic_picker_step(
        self,
        *,
        step_id: str,
        conf_key: str,
        device_cls: type,
        user_input: dict[str, Any] | None,
    ) -> ConfigFlowResult:
        """Render / handle a device-picker step for one device type."""
        if user_input is not None:
            self.options[conf_key] = user_input[conf_key]
            self._pending_pickers.pop(0)
            return await self._advance_optimistic_picker()

        coordinator = self.hass.data[DOMAIN][self.config_entry.entry_id]["coordinator"]
        devices = {
            device_id: device.name
            for device_id, device in coordinator.devices.items()
            if isinstance(device, device_cls)
        }

        if not devices:
            # No devices of this type to pick from — skip to next picker.
            self.options[conf_key] = []
            self._pending_pickers.pop(0)
            return await self._advance_optimistic_picker()

        stored = self.options.get(conf_key)
        default = stored if isinstance(stored, list) else list(devices.keys())

        return self.async_show_form(
            step_id=step_id,
            data_schema=vol.Schema(
                {
                    vol.Required(conf_key, default=default): cv.multi_select(devices),
                }
            ),
        )
```

### Step 4: Add three picker step methods

- [ ] **Step 4: Add per-type wrapper steps**

```python
    async def async_step_pick_lights(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Pick which light devices are optimistic."""
        return await self._optimistic_picker_step(
            step_id="pick_lights",
            conf_key=CONF_OPTIMISTIC_LIGHTS,
            device_cls=UhomeLight,
            user_input=user_input,
        )

    async def async_step_pick_switches(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Pick which switch devices are optimistic."""
        return await self._optimistic_picker_step(
            step_id="pick_switches",
            conf_key=CONF_OPTIMISTIC_SWITCHES,
            device_cls=UhomeSwitch,
            user_input=user_input,
        )

    async def async_step_pick_locks(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Pick which lock devices are optimistic."""
        return await self._optimistic_picker_step(
            step_id="pick_locks",
            conf_key=CONF_OPTIMISTIC_LOCKS,
            device_cls=UhomeLock,
            user_input=user_input,
        )
```

### Step 5: Update `strings.json`

- [ ] **Step 5: Add picker translations**

Inside `options.step`, alongside `optimistic_updates`:

```json
"pick_lights": {
  "title": "Optimistic Lights",
  "description": "Select the light devices that should use optimistic updates. Unselected lights will wait for confirmed state.",
  "data": {
    "optimistic_lights": "Optimistic lights"
  }
},
"pick_switches": {
  "title": "Optimistic Switches",
  "description": "Select the switch devices that should use optimistic updates. Unselected switches will wait for confirmed state.",
  "data": {
    "optimistic_switches": "Optimistic switches"
  }
},
"pick_locks": {
  "title": "Optimistic Locks",
  "description": "Select the lock devices that should use optimistic updates. Unselected locks will wait for confirmed state.",
  "data": {
    "optimistic_locks": "Optimistic locks"
  }
}
```

Mirror under `translations/` if present.

### Step 6: Manual verification

- [ ] **Step 6: Verify the full flow**

1. Restart HA.
2. Integrations → Uhome → Configure → Configure Optimistic Updates.
3. Set lights = `custom`, switches = `none`, locks = `all`.
4. Picker step for lights should appear; confirm it lists lights only.
5. Submit the picker; form closes.
6. Re-open to verify persistence:
   - `options["optimistic_switches"] == False`
   - `options["optimistic_locks"] == True`
   - `options["optimistic_lights"] == ["dev-x", ...]`
7. Open a light device in the UI; assumed-state behaviour should match the selection.

### Step 7: Commit

- [ ] **Step 7: Commit**

```bash
git add custom_components/u_tec/config_flow.py custom_components/u_tec/strings.json
git commit -m "Add per-type device pickers to optimistic-updates flow"
```

---

## Final verification checklist

After all tasks are committed, run through each scenario end-to-end.

**Resolver tests**
- [ ] `.venv/bin/pytest` → 8 tests pass.

**Default behavior (no options change)**
- [ ] Fresh install with no options changes behaves exactly as today — optimistic writes still occur for lights, switches, locks.

**All off**
- [ ] Set lights/switches/locks all to `None` via flow. Toggle a light → UI does not flip instantly; state changes only on next coordinator poll (default 10s) or push update.

**Custom mix**
- [ ] Lights = `custom` with only device A selected. Toggle A → optimistic UI update occurs. Toggle B → UI waits for poll.

**Persistence across restart**
- [ ] Restart HA; verify `entry.options` still contains the mode choices and picker selections.

**assumed_state badge**
- [ ] Switch in `None` mode → HA UI no longer shows the "assumed" badge.
- [ ] Switch in `All` mode → badge visible.

**No regressions**
- [ ] Push update flow still works (Options → Update Push Status unchanged).
- [ ] Active-devices flow still works (Options → Select Active Devices unchanged).

---

## Execution handoff

Plan complete and saved to `docs/superpowers/plans/2026-04-18-optimistic-update-flags.md`. Two execution options:

1. **Subagent-Driven (recommended)** — fresh subagent per task, review between tasks, fast iteration.
2. **Inline Execution** — execute tasks in this session using executing-plans, batch execution with checkpoints.

Which approach?
