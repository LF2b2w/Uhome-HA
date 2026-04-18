# Optimistic-Update Configuration Flags — Design

**Date:** 2026-04-18
**Component:** `custom_components/u_tec` (Uhome-HA integration)
**Status:** Design approved, pending implementation plan

## Background

Three platforms in the Uhome integration apply optimistic state updates today:
`light.py`, `switch.py`, and `lock.py`. Each entity sets a private
`_optimistic_*` field and calls `async_write_ha_state()` immediately after a
successful API call, then clears the optimistic state once the coordinator
confirms the real device state.

Some users want to disable this behavior — for example when they prefer to see
only confirmed device state, when the device is reporting delayed state that
conflicts with optimistic writes, or for classes of device where premature UI
updates cause flicker.

The `sensor.py` and `binary_sensor.py` platforms are read-only and do not apply
optimistic updates, so they are out of scope.

## Goals

- Per-device-type toggle for optimistic updates (lights, switches, locks).
- Support three modes per type: all devices of that type, no devices of that
  type, or a user-selected subset.
- Default behavior (no configuration present) preserves today's "always
  optimistic" behavior for backwards compatibility.
- Configuration lives in the existing OAuth-based options flow UI, consistent
  with the existing `push_enabled` / `push_devices` pattern. No YAML changes
  required.

## Non-goals

- Per-attribute granularity (e.g. optimistic `is_on` but not optimistic
  `brightness`). Light gates both fields behind a single light-level flag.
- Migrating existing config entries. The new option keys are simply absent on
  existing entries and resolve to the default.
- Configuration via `configuration.yaml`. All configuration lives in
  `entry.options`.

## Data model

### Option keys (in `const.py`)

```python
CONF_OPTIMISTIC_LIGHTS = "optimistic_lights"
CONF_OPTIMISTIC_SWITCHES = "optimistic_switches"
CONF_OPTIMISTIC_LOCKS = "optimistic_locks"
DEFAULT_OPTIMISTIC = True
```

### Value shape

Each key in `entry.options` holds one of:

| Value | Meaning |
| --- | --- |
| *absent* | Defaults to `True` (all devices of this type optimistic) |
| `True` | All devices of this type optimistic |
| `False` | No devices of this type optimistic |
| `list[str]` | Only the listed device IDs are optimistic; all other devices of this type are not |

### Resolver helper

One shared pure function, called by all three platforms:

```python
def is_optimistic_enabled(
    options: Mapping[str, Any],
    conf_key: str,
    device_id: str,
) -> bool:
    value = options.get(conf_key, DEFAULT_OPTIMISTIC)
    if isinstance(value, bool):
        return value
    return device_id in value
```

The function lives alongside the constants (either in `const.py` or a new
`helpers.py`; decided at implementation time). The implementation plan may
place it wherever best matches the existing module layout.

## Configuration UI

### Menu entry

`OptionsFlowHandler.async_step_init` adds a new menu option:

```python
menu_options={
    "update_push": "Update Push Status",
    "get_devices": "Select Active Devices",
    "optimistic_updates": "Configure Optimistic Updates",
}
```

### Mode selection step — `async_step_optimistic_updates`

A single form with three required fields, each a `SelectSelector` offering
`all`, `none`, `custom`:

- `lights_mode`
- `switches_mode`
- `locks_mode`

Defaults are inferred from the current option values:

| Stored value | Default mode shown |
| --- | --- |
| absent | `all` |
| `True` | `all` |
| `False` | `none` |
| `list[str]` | `custom` |

On submit, the handler normalises each type:

- `all` → `entry.options[CONF_OPTIMISTIC_<TYPE>] = True`
- `none` → `entry.options[CONF_OPTIMISTIC_<TYPE>] = False`
- `custom` → defer until the picker step collects device IDs

If any type is `custom`, the flow proceeds to the picker steps below in a
fixed order (lights, switches, locks). Each picker runs only if its type is
`custom`. When no pickers remain, `async_create_entry` is called.

### Picker steps

Three picker steps:

- `async_step_pick_lights`
- `async_step_pick_switches`
- `async_step_pick_locks`

Each shows a single `cv.multi_select` populated from coordinator devices
filtered to the appropriate category (same mechanism as
`async_step_get_devices` already uses). The default selection reflects the
currently-stored list, if any. Submit writes `list[str]` into the matching
option key and advances to the next pending picker or finalises.

### Strings

`strings.json` and the relevant translation files gain the new step keys,
field labels, and helper text.

## Entity integration

All three platform files (`light.py`, `switch.py`, `lock.py`) are modified to
gate their optimistic writes behind the resolver.

### Turn-on / turn-off path

Each place that currently writes `_optimistic_*` and calls
`async_write_ha_state()` now first asks the resolver. Example (switch):

```python
async def async_turn_on(self, **kwargs):
    result = await self._device.turn_on()
    if not result.get("error"):
        if is_optimistic_enabled(
            self.coordinator.config_entry.options,
            CONF_OPTIMISTIC_SWITCHES,
            self._device.id,
        ):
            self._optimistic_is_on = True
            self.async_write_ha_state()
```

When optimistic is off for this device, no optimistic field is set and no
premature `async_write_ha_state()` is called. The entity reflects only the
coordinator poll or webhook push.

Light is identical in shape but gates both `_optimistic_is_on` and
`_optimistic_brightness` behind the single lights flag. Lock gates
`_optimistic_is_locked`.

### `assumed_state` property

Each entity also exposes `assumed_state` so Home Assistant's UI shows the
"assumed" badge correctly:

```python
@property
def assumed_state(self) -> bool:
    return is_optimistic_enabled(
        self.coordinator.config_entry.options,
        CONF_OPTIMISTIC_<TYPE>,
        self._device.id,
    )
```

Badge visible when optimistic is enabled for that device, hidden when the
state is trusted.

### Entity access to options

The resolver needs access to `entry.options`. Entities hold a reference to
the coordinator, which is constructed with access to the entry. If
`coordinator.config_entry` is not already available, the entity constructor
captures a reference to the entry. Final wiring decided during
implementation.

## Runtime behavior on options change

`async_update_options` already calls
`hass.config_entries.async_reload(entry.entry_id)`, which tears down and
recreates entities. This means:

- Any in-flight optimistic state is cleared naturally when the entity is
  rebuilt (approach B from brainstorming).
- New optimistic flag values take effect on the first turn-on/turn-off
  after reload.

No additional teardown or state-clearing logic is required.

## Backwards compatibility

- Existing config entries do not have any `optimistic_*` keys in their
  options dict.
- The resolver defaults missing keys to `True`, matching today's unconditional
  optimistic behavior.
- No schema version bump, no migration step.

## Testing

A minimal pytest harness is added for the resolver:

- New file: `tests/test_optimistic.py`
- Covers the pure `is_optimistic_enabled` function.
- Cases: key absent → `True`; key `True` → `True`; key `False` → `False`;
  key `list[str]` with match → `True`; key `list[str]` without match →
  `False`; empty list → `False`.

No Home Assistant fixtures required. Manual QA covers the options flow UI
and entity wiring, with a checklist produced in the implementation plan.
Broader `pytest-homeassistant-custom-component` test infrastructure is out
of scope for this change.

## Open questions

None at design time. Implementation plan will resolve final file placement
for the resolver helper and confirm entity access to `entry.options`.
