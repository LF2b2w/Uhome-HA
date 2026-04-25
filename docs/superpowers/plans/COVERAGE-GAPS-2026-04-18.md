# Coverage Gap Punch List — 2026-04-24 (Task 24a)

**Baseline:** 82.69% total. Target: 85% overall, per-module floors vary.  
**Scope:** Files below 85% that need additional tests.  
**Letters assigned:** 24b (lock.py) · 24c (light.py) · 24d (switch.py) · 24e (__init__.py) · 24f (config_flow.py)

---

## Module: custom_components/u_tec/lock.py (current: 69%)

**Task 24 letter: b**

- Uncovered lines: `34-38, 77, 82-84, 94, 103-111, 132->exit, 135-137, 144->exit, 147-149, 153-155, 166`
- 21 missed statements, 2 missed branches

### Gap details

| Range | Nature | Recommended test | Effort |
|-------|--------|-----------------|--------|
| 34-38 | simple branch | Coordinator contains non-lock devices; verify isinstance filter excludes them from async_add_entities | trivial |
| 77 | simple branch | Mock `coordinator.last_update_success=False` or `device.available=False` and assert `available` returns False | trivial |
| 82-84 | simple branch | Set `_optimistic_is_locked` to True; assert `is_locked` returns the optimistic value, not `device.is_locked` | trivial |
| 94 | simple branch | Access `is_jammed` property with `device.is_jammed=True`; assert True returned | trivial |
| 103-111 | simple branch | Set `_optimistic_is_locked=True`, trigger `_handle_coordinator_update` with `device.is_locked` still False (not confirmed); assert state not cleared. Then confirm with matching value; assert cleared | moderate |
| 132->exit | defensive log-only | Mock `device.lock()` to raise `DeviceError`; assert error path branch taken (no optimistic write, exception raised) | trivial |
| 135-137 | defensive log-only | Mock `device.lock()` raise; assert `_LOGGER.error` called and `HomeAssistantError` raised | trivial |
| 144->exit | defensive log-only | Mock `device.unlock()` raise; assert error exit branch taken | trivial |
| 147-149 | defensive log-only | Mock `device.unlock()` raise; assert error log + `HomeAssistantError` | trivial |
| 153-155 | framework-callback | Call `async_added_to_hass`; assert `async_dispatcher_connect` invoked with correct signal | trivial |
| 166 | framework-callback | Fire `SIGNAL_DEVICE_UPDATE_<id>` dispatcher signal; assert `async_write_ha_state` called | trivial |

**Estimated effort:** moderate (most items trivial; one moderate for coordinator-update reconciliation)

---

## Module: custom_components/u_tec/light.py (current: 78%)

**Task 24 letter: c**

- Uncovered lines: `45-49, 100->102, 103, 105, 109, 113, 115, 119, 132, 138, 144-148, 185, 192, 206, 209, 213->exit, 229->exit, 240-242, 253`
- 22 missed statements, 12 missed branches

### Gap details

| Range | Nature | Recommended test | Effort |
|-------|--------|-----------------|--------|
| 45-49 | simple branch | Coordinator with non-light devices; verify isinstance filter | trivial |
| 100->102 | simple branch | Set `_optimistic_is_on=True`; assert `is_on` returns optimistic value | trivial |
| 103 | simple branch | Clear optimistic state; assert `is_on` delegates to `device.is_on` | trivial |
| 105 | simple branch | Set `_optimistic_brightness`; assert `brightness` returns it | trivial |
| 109 | simple branch | `device.brightness=None`; assert `brightness` returns None | trivial |
| 113 | simple branch | `device.brightness=50`; assert `brightness` returns `value_to_brightness((1,100), 50)` | trivial |
| 115 | simple branch | Set `_optimistic_is_on=True` with optimistic mode on; assert `assumed_state` True | trivial |
| 119 | simple branch | Set `_optimistic_brightness` only; assert `assumed_state` True | trivial |
| 132 | simple branch | Set `_optimistic_is_on=True`, update device to `is_on=True`; assert optimistic state cleared | moderate |
| 138 | simple branch | Set pending brightness; trigger update with matching `device.brightness`; assert pending + optimistic cleared | moderate |
| 144-148 | simple branch | `_pending_brightness_utec=None`; trigger `_handle_coordinator_update`; assert `_optimistic_brightness` cleared via else branch | moderate |
| 185 | simple branch | Access `rgb_color` property; assert it returns `device.rgb_color` | trivial |
| 192 | simple branch | Access `color_temp_kelvin` property; assert it returns `device.color_temp` | trivial |
| 206, 209 | defensive log-only | Mock `device.turn_on()` raise `DeviceError`; assert log + `HomeAssistantError` | trivial |
| 213->exit | simple branch | Disable optimistic mode (`CONF_OPTIMISTIC_LIGHTS=False`); call `async_turn_off`; assert no optimistic write, no exit via error | trivial |
| 229->exit | defensive log-only | Mock `device.turn_off()` raise `DeviceError`; assert error exit path taken | trivial |
| 240-242 | framework-callback | Call `async_added_to_hass`; assert dispatcher connected | trivial |
| 253 | framework-callback | Fire push signal; assert `async_write_ha_state` called | trivial |

**Estimated effort:** moderate (3 moderate coordinator-update items, rest trivial)

---

## Module: custom_components/u_tec/switch.py (current: 78%)

**Task 24 letter: d**

- Uncovered lines: `35-39, 78, 83-85, 94->98, 95->98, 105->exit, 119->exit, 122-126, 130-132, 143`
- 12 missed statements, 4 missed branches

### Gap details

| Range | Nature | Recommended test | Effort |
|-------|--------|-----------------|--------|
| 35-39 | simple branch | Coordinator with non-switch devices; verify isinstance filter exclusion | trivial |
| 78 | simple branch | `coordinator.last_update_success=False`; assert `available` returns False | trivial |
| 83-85 | simple branch | Set `_optimistic_is_on=True`; assert `is_on` returns optimistic value; clear it and assert falls back | trivial |
| 94->98, 95->98 | simple branch | Set `_optimistic_is_on` and verify `assumed_state` evaluates True; clear and verify False | trivial |
| 105->exit | defensive log-only | Mock `device.turn_on()` raise; assert error path exit taken (no optimistic write) | trivial |
| 119->exit | defensive log-only | Mock `device.turn_off()` raise; assert error path exit | trivial |
| 122-126 | defensive log-only | Mock `device.turn_on()` raise `DeviceError`; assert `_LOGGER.error` + `HomeAssistantError` | trivial |
| 130-132 | defensive log-only | Mock `device.turn_off()` raise `DeviceError`; assert error log + exception | trivial |
| 143 | framework-callback | Call `async_added_to_hass`; assert dispatcher connection established | trivial |

**Estimated effort:** trivial (all items are straightforward branch/error-path coverage)

---

## Module: custom_components/u_tec/__init__.py (current: 84%)

**Task 24 letter: e**

- Uncovered lines: `59-67, 160-165`
- 8 missed statements, 1 missed branch

### Gap details

| Range | Nature | Recommended test | Effort |
|-------|--------|-----------------|--------|
| 59-67 | environment-dependent | Call `async_setup` with config dict containing `DOMAIN` key and `CONF_SCAN_INTERVAL`/`CONF_DISCOVERY_INTERVAL` values; assert stored in `hass.data` and debug log fired | moderate |
| 160-165 | environment-dependent | Create a `MockConfigEntry` with `version=1`; call `async_migrate_entry`; assert it completes and migrates data to version 2 format | moderate |

**Estimated effort:** moderate (both require constructing specific entry/config state; neither is complex)

---

## Module: custom_components/u_tec/config_flow.py (current: 73%)

**Task 24 letter: f**

- Uncovered lines: `83, 88, 96-97, 177-182, 201-216, 258->248, 312-314, 345, 357, 369-381, 385-397`
- 36 missed statements, 4 missed branches
- Note: config_flow has 36 missing statements spanning multiple unrelated flow steps. Grouping as one letter because all gaps are options/flow UI branches — same fixture shape throughout. Split to 24f + 24g if implementation reveals >8 unrelated concerns.

### Gap details

| Range | Nature | Recommended test | Effort |
|-------|--------|-----------------|--------|
| 83 | simple branch | Pre-create existing u_tec entry; call `async_step_user`; assert aborts with `single_instance_allowed` | trivial |
| 88 | simple branch | Call `async_step_user` with valid `user_input`; assert transitions to `pick_implementation` | trivial |
| 96-97 | simple branch | Submit form in `async_step_user` with `user_input=None`; assert form rendered (no errors dict path) | trivial |
| 177-182 | simple branch | Instantiate handler with existing entry; call `async_step_reauth`; assert delegates to `reauth_confirm` | trivial |
| 201-216 | simple branch | Call `async_step_reauth_confirm` with non-None `user_input`; assert proceeds to `async_step_user` | trivial |
| 258->248 | simple branch | Instantiate `OptionsFlowHandler`; call `async_step_init`; assert menu shown | trivial |
| 312-314 | simple branch | In `async_step_update_push`, submit `user_input={CONF_PUSH_ENABLED: True}`; assert advances to `push_device_selection` | trivial |
| 345 | simple branch | Call `async_step_optimistic_updates` with no input; assert form rendered with default mode values | trivial |
| 357 | simple branch | Call `_advance_optimistic_picker` with one pending key; assert dispatches to correct step | trivial |
| 369-381 | simple branch | Test `_optimistic_picker_step` with zero matching devices (skip branch) and with devices present (form branch) | moderate |
| 385-397 | simple branch | Call `async_step_pick_lights`, `async_step_pick_switches`, `async_step_pick_locks` with no user_input; assert form rendered per type | moderate |

**Estimated effort:** moderate (many trivial items; two moderate for multi-branch picker logic)

---

## Summary

| Letter | Module | Current | Target | Missing stmts | Effort |
|--------|--------|---------|--------|--------------|--------|
| 24b | lock.py | 69% | ≥85% | 21 | moderate |
| 24c | light.py | 78% | ≥85% | 22 | moderate |
| 24d | switch.py | 78% | ≥85% | 12 | trivial |
| 24e | __init__.py | 84% | ≥80% (meets floor; helps total) | 8 | moderate |
| 24f | config_flow.py | 73% | (no floor; contributes to 85% total) | 36 | moderate |

**Estimated total effort:** 3–5 engineering sessions of moderate complexity each.  
Completing 24b + 24c + 24d alone should cross the 85% total threshold; 24e and 24f provide margin.
