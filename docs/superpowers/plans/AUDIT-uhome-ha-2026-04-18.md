# Uhome-HA audit — 2026-04-18

> Compact reference for test-coverage plan subagents. Every identifier is
> transcribed verbatim from source. Do not invent names — read this file
> instead of re-reading the source.

---

## custom_components/u_tec/__init__.py

**Module-level symbols**
- `_PLATFORMS: list[Platform]` = `[Platform.LOCK, Platform.LIGHT, Platform.SWITCH, Platform.SENSOR]`
- `_YAML_CONFIG_KEY = "_yaml_config"` — key inside `hass.data[DOMAIN]` for YAML-sourced config
- `CONFIG_SCHEMA` — optional `scan_interval` (positive int, min 1) and `discovery_interval` (positive int, min 10)

**Functions**
- `async_setup(hass: HomeAssistant, config: dict) -> bool`
  - Stores `config[DOMAIN]` under `hass.data[DOMAIN][_YAML_CONFIG_KEY]` when present; always returns `True`
- `async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool`
  - Flow: `async_get_config_entry_implementation` → `OAuth2Session` → `AsyncConfigEntryAuth` → `UHomeApi`
  - Reads yaml_config for `scan_interval` / `discovery_interval` (falls back to defaults)
  - Constructs `UhomeDataUpdateCoordinator(hass, Uhomeapi, config_entry=entry, scan_interval=..., discovery_interval=...)`
  - Calls `coordinator.async_discover_devices()` then `coordinator.async_config_entry_first_refresh()`
  - Calls `coordinator.async_start_periodic_discovery()`
  - Constructs `AsyncPushUpdateHandler(hass, Uhomeapi, entry.entry_id)`
  - Reads `entry.options.get(CONF_PUSH_ENABLED, True)` and `entry.options.get(CONF_PUSH_DEVICES, [])`
  - Sets `coordinator.push_devices = push_devices`
  - If push enabled: `await webhook_handler.async_register_webhook(auth_data)`
  - Stores `hass.data[DOMAIN][entry.entry_id]` = `{"api": ..., "coordinator": ..., "auth_data": ..., "webhook_handler": ...}`
  - Registers unload callbacks: `async_update_options`, `webhook_handler.unregister_webhook`, `coordinator.async_stop_periodic_discovery`
- `async_update_options(hass: HomeAssistant, entry: ConfigEntry) -> None`
  - Reads `entry.data.get("options", {}).get(CONF_PUSH_ENABLED, True)` as old value
  - Reads `entry.options.get(CONF_PUSH_ENABLED, True)` as new value
  - Updates `coordinator.push_devices = entry.options.get(CONF_PUSH_DEVICES, [])`
  - If toggle changed: registers or calls `webhook_handler.unregister_webhook()`
  - Always calls `hass.config_entries.async_reload(entry.entry_id)`
- `async_migrate_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool`
  - Migrates `config_entry.version < 2` → pops `CONF_CLIENT_SECRET` and `CONF_CLIENT_ID` from data
  - Updates entry with `version=2, minor_version=1`; returns `True`

---

## custom_components/u_tec/const.py

**Defined directly in const.py**
- `DOMAIN = "u_tec"`
- `CONF_SCAN_INTERVAL = "scan_interval"`
- `CONF_DISCOVERY_INTERVAL = "discovery_interval"`
- `DEFAULT_SCAN_INTERVAL = 10`  (seconds)
- `DEFAULT_DISCOVERY_INTERVAL = 300`  (seconds, 5 minutes)
- `OAUTH2_AUTHORIZE = "https://oauth.u-tec.com/authorize"`
- `OAUTH2_TOKEN = "https://oauth.u-tec.com/token"`
- `CONF_API_SCOPE = "scope"`
- `CONF_PUSH_ENABLED = "push_enabled"`
- `CONF_PUSH_DEVICES = "push_devices"`
- `CONF_HA_DEVICES = "HomeAssistant_devices"`
- `DEFAULT_API_SCOPE = "openapi"`
- `API_BASE_URL = "https://api.u-tec.com/action"`
- `SIGNAL_NEW_DEVICE = f"{DOMAIN}_new_device"`  → `"u_tec_new_device"`
- `SIGNAL_DEVICE_UPDATE = f"{DOMAIN}_device_update"`  → `"u_tec_device_update"`
- `WEBHOOK_ID_PREFIX = "u_tec_push_"`
- `WEBHOOK_HANDLER = 'u_tec_webhook_handler'`

**Re-exported from optimistic.py** (imported at top of const.py)
- `CONF_OPTIMISTIC_LIGHTS`
- `CONF_OPTIMISTIC_SWITCHES`
- `CONF_OPTIMISTIC_LOCKS`
- `DEFAULT_OPTIMISTIC`
- `is_optimistic_enabled`

---

## custom_components/u_tec/coordinator.py

**Class: `UhomeDataUpdateCoordinator(DataUpdateCoordinator)`**

Constructor:
```python
def __init__(
    self,
    hass: HomeAssistant,
    api: UHomeApi,
    config_entry: ConfigEntry,
    scan_interval: int = DEFAULT_SCAN_INTERVAL,
    discovery_interval: int = DEFAULT_DISCOVERY_INTERVAL,
) -> None
```
Instance attributes set in `__init__`:
- `self.api: UHomeApi`
- `self.config_entry: ConfigEntry`
- `self.devices: dict[str, BaseDevice] = {}`
- `self.added_sensor_entities = set()`
- `self.push_devices = []`
- `self.blacklisted_devices = []`
- `self._discovery_interval = timedelta(seconds=discovery_interval)`
- `self._cancel_discovery: callable | None = None`

**Methods**
- `async async_start_periodic_discovery(self) -> None`
  - Cancels existing `_cancel_discovery` if set
  - Registers `async_track_time_interval(hass, self._async_scheduled_discovery, self._discovery_interval)`
- `async_stop_periodic_discovery(self) -> None`  *(sync, not async)*
  - Cancels and clears `self._cancel_discovery`
- `async async_discover_devices(self) -> None`
  - Calls `self.api.discover_devices()`; returns early on `ApiError` / `AuthenticationError`
  - Returns early if no `"payload"` key in response
  - Iterates `discovery_data["payload"]["devices"]`; skips existing device IDs
  - **handleType dispatch order** (exact substring checks on `.lower()` result):
    1. `"lock" in handle_type` → `Lock(device_data, self.api)`
    2. `"dimmer" in handle_type or "light" in handle_type or "bulb" in handle_type` → `Light(device_data, self.api)`
    3. `"switch" in handle_type` → `Switch(device_data, self.api)`
    4. else → `continue` (skip, log debug)
  - After processing all new devices: bulk `self.api.get_device_state(new_device_ids, None)`
  - Fires `async_dispatcher_send(self.hass, SIGNAL_NEW_DEVICE)` per new device
- `async _async_scheduled_discovery(self, _now) -> None`
  - Simply calls `await self.async_discover_devices()`
- `async _async_update_data(self) -> dict[str, dict]`
  - Returns `{}` if `self.devices` is empty
  - Calls `self.api.get_device_state(device_ids, None)`
  - `AuthenticationError` → raises `ConfigEntryAuthFailed`
  - `ApiError` → raises `UpdateFailed`
  - Calls `device.update_state_data(device_data)` for each matched device
  - Returns `{device_id: device.get_state_data() for device_id, device in self.devices.items()}`
- `async update_push_data(self, push_data) -> None`
  - **Normalisation branches** (exact logic):
    - `isinstance(push_data, list)` → `devices_data = push_data`  (flat list — shape b)
    - `isinstance(push_data, dict)`:
      - `payload = push_data.get("payload", {})`
      - `isinstance(payload, list)` → `devices_data = payload`
      - `isinstance(payload, dict)` → `raw = payload.get("devices", [])`; if `isinstance(raw, list)`: `devices_data = raw`; else: warning
      - else (payload not list/dict): warning
    - else (not list/dict): warning
  - Skips device if `self.push_devices` is non-empty and `device_id not in self.push_devices`
  - On match: calls `device.update_state_data(device_data)` then `async_dispatcher_send(hass, f"{SIGNAL_DEVICE_UPDATE}_{device_id}", device.get_state_data())`
  - Calls `self.async_set_updated_data(self.data)` at end
  - Catches `(ValueError, TypeError, AttributeError)`

---

## custom_components/u_tec/api.py

**Class: `AsyncConfigEntryAuth(AbstractAuth)`**

```python
def __init__(
    self,
    websession: ClientSession,
    oauth_session: config_entry_oauth2_flow.OAuth2Session,
) -> None
```
- `async async_get_access_token(self) -> str`
  - Calls `await self._oauth_session.async_ensure_token_valid()`
  - Returns `self._oauth_session.token["access_token"]`

**Class: `AsyncPushUpdateHandler`**

```python
def __init__(self, hass: HomeAssistant, api: UHomeApi, entry_id: str) -> None
```
Instance attributes:
- `self.hass`
- `self.entry_id`
- `self.webhook_id = f"{WEBHOOK_ID_PREFIX}{entry_id}"`
- `self.webhook_url = None`
- `self._unregister_webhook = None`
- `self._cancel_reregister = None`
- `self._push_secret: str | None = None`
- `self.api`
- `self._auth_data = None`

Methods:
- `_generate_secret(self) -> str`
  - Returns `secrets.token_urlsafe(32)`
- `async async_register_webhook(self, auth_data) -> bool`
  - URL resolution strategy loop — three `(allow_internal, allow_ip, prefer_cloud)` triples tried in order:
    1. `(False, False, False)`
    2. `(False, False, True)`
    3. `(True, True, False)`
  - Returns `False` if no external URL found
  - Logs warning if webhook URL contains any of: `"192.168."`, `"10."`, `"172."`, `"homeassistant.local"`, `"localhost"`, `"127.0."`
  - Generates new `self._push_secret` via `_generate_secret()`
  - Calls `await self.api.set_push_status(webhook_url, self._push_secret)`; returns `False` on `ApiError`
  - Registers HA-side webhook only if `not self._unregister_webhook`
  - Schedules `_async_reregister` every `_REREGISTER_INTERVAL = timedelta(hours=24)`
  - Returns `True` on success
- `_async_reregister(self, _now) -> None`  *(sync `@callback`)*
  - Calls `self.hass.async_create_task(self.async_register_webhook(self._auth_data))`
- `async unregister_webhook(self) -> None`
  - Cancels `_cancel_reregister`
  - Calls `webhook.async_unregister(self.hass, self.webhook_id)`
  - Clears `self._unregister_webhook = None`
- `async _handle_webhook(self, hass: HomeAssistant, webhook_id, request) -> web.Response | None`
  - **HTTP status codes returned** and their branches:
    - `405` — `request.method != "POST"`
    - `400` — JSON parse fails (`json.loads` raises)
    - `401` — `Authorization` header missing or empty Bearer token
    - `403` — Bearer token does not match `self._push_secret` (via `secrets.compare_digest`)
    - `404` — `self.entry_id not in hass.data.get(DOMAIN, {})`
    - `400` (json_response) — `UHomeError` caught in outer except (returns `{"success": False, "error": str(err)}`)
    - `500` (json_response) — bare `Exception` caught (returns `{"success": False, "error": "Internal error"}`)
    - `200` (json_response) — success else-branch: `{"success": True}`
  - Auth check only runs when `self._push_secret is not None`
  - On success: calls `coordinator.update_push_data(data)`

---

## custom_components/u_tec/config_flow.py

**Module-level constants**
- `OPTIMISTIC_MODE_ALL = "all"`
- `OPTIMISTIC_MODE_NONE = "none"`
- `OPTIMISTIC_MODE_CUSTOM = "custom"`
- `OPTIMISTIC_MODES = [OPTIMISTIC_MODE_ALL, OPTIMISTIC_MODE_NONE, OPTIMISTIC_MODE_CUSTOM]`  (ordered list)
- `STEP_USER_DATA_SCHEMA` — `vol.Optional(CONF_API_SCOPE, default=DEFAULT_API_SCOPE): str`

**Function: `_current_mode(value: bool | list[str] | None) -> str`**
- `value is True or value is None` → returns `"all"`
- `value is False` → returns `"none"`
- else (list) → returns `"custom"`

**Class: `UhomeOAuth2FlowHandler(config_entry_oauth2_flow.AbstractOAuth2FlowHandler, domain=DOMAIN)`**

Class attributes:
- `DOMAIN = DOMAIN`  (i.e. `"u_tec"`)
- `VERSION = 2`

Instance attributes (from `__init__`):
- `self._api_scope = None`
- `self.data = {}`

Properties:
- `logger` → returns `_LOGGER`
- `extra_authorize_data` → returns `{"scope": self._api_scope or DEFAULT_API_SCOPE}`

Methods:
- `async async_step_user(self, user_input=None) -> ConfigFlowResult`
  - Aborts with `reason="single_instance_allowed"` if entries exist
  - On submit: stores `self.data = user_input`, redirects to `async_step_pick_implementation()`
  - Shows form with `step_id="user"`
- `async async_oauth_create_entry(self, data: dict) -> config_entries.ConfigFlowResult`
  - Creates entry with default options: `{CONF_PUSH_ENABLED: True, CONF_PUSH_DEVICES: [], CONF_HA_DEVICES: []}`
- `async async_step_reauth(self, entry_data: Mapping[str, vol.Any]) -> ConfigFlowResult`
  - Delegates to `async_step_reauth_confirm(entry_data)`
- `async async_step_reauth_confirm(self, user_input: Mapping[str, vol.Any] | None = None) -> ConfigFlowResult`
  - If `user_input is None`: shows form with `step_id="reauth_confirm"`, `data_schema=vol.Schema({})`
  - Else: calls `async_step_user()`
- `async_get_options_flow(config_entry)` (static `@callback`) → returns `OptionsFlowHandler(config_entry)`

**Class: `OptionsFlowHandler(config_entries.OptionsFlow)`**

```python
def __init__(self, config_entry: ConfigEntry) -> None
```
Instance attributes:
- `self.api = None`
- `self.devices = {}`
- `self.options = dict(config_entry.options)`
- `self._pending_pickers: list[str] = []`

**step_ids — complete list (verbatim from source)**:

| step_id | method | notes |
|---|---|---|
| `"user"` | `async_step_user` | OAuth config flow |
| `"reauth_confirm"` | `async_step_reauth_confirm` | reauth dialog |
| `"init"` | `async_step_init` | menu step |
| `"update_push"` | `async_step_update_push` | push enable/disable form |
| `"push_device_selection"` | `async_step_push_device_selection` | multi-select push devices |
| `"optimistic_updates"` | `async_step_optimistic_updates` | 3-dropdown mode picker |
| `"pick_lights"` | `async_step_pick_lights` | custom light device picker |
| `"pick_switches"` | `async_step_pick_switches` | custom switch device picker |
| `"pick_locks"` | `async_step_pick_locks` | custom lock device picker |
| `"device_selection"` | `async_step_device_selection` | active-device picker (get_devices branch) |

**`async_step_init` menu_options** (exact keys and display strings):
```python
{
    "update_push": "Update Push Status",
    "get_devices": "Select Active Devices",
    "optimistic_updates": "Configure Optimistic Updates",
}
```

**`async_step_update_push`**
- Form: `CONF_PUSH_ENABLED` (BooleanSelector, default from options)
- On submit: if enabled → `async_step_push_device_selection()`; if disabled → `async_create_entry(title="", data=self.options)`

**`async_step_push_device_selection`**
- Reads `coordinator.devices` to build `{device_id: device.name}` dict
- Default selection: stored `CONF_PUSH_DEVICES` or all device IDs if empty
- On submit: stores `self.options[CONF_PUSH_DEVICES]` and creates entry

**`async_step_optimistic_updates`**
- Schema fields: `"lights_mode"`, `"switches_mode"`, `"locks_mode"` (all `SelectSelector`, `OPTIMISTIC_MODES` options, `SelectSelectorMode.DROPDOWN`, `translation_key="optimistic_mode"`)
- Default per field: calls `_current_mode(self.options.get(CONF_OPTIMISTIC_<TYPE>))`
- On submit: iterates `(CONF_OPTIMISTIC_LIGHTS, "lights_mode")`, `(CONF_OPTIMISTIC_SWITCHES, "switches_mode")`, `(CONF_OPTIMISTIC_LOCKS, "locks_mode")`
  - `"all"` → `self.options[conf_key] = True`
  - `"none"` → `self.options[conf_key] = False`
  - `"custom"` → appends `conf_key` to `self._pending_pickers`
- Calls `await self._advance_optimistic_picker()`

**`_advance_optimistic_picker(self) -> ConfigFlowResult`** (private, not a step)
- If `self._pending_pickers` is empty → `async_create_entry(title="", data=self.options)`
- Else pops `self._pending_pickers[0]` and dispatches:
  - `CONF_OPTIMISTIC_LIGHTS` → `self.async_step_pick_lights()`
  - `CONF_OPTIMISTIC_SWITCHES` → `self.async_step_pick_switches()`
  - `CONF_OPTIMISTIC_LOCKS` → `self.async_step_pick_locks()`

**`_optimistic_picker_step(self, *, step_id, conf_key, device_cls, user_input)` (private helper)**
- Renders form with `step_id=step_id` and `cv.multi_select(devices)` for `conf_key`
- If no devices of `device_cls` found: sets `self.options[conf_key] = []`, pops picker, advances
- Default selection: stored value if list, else all device IDs

**`async_step_pick_lights(self, user_input=None)`**
- Delegates to `_optimistic_picker_step(step_id="pick_lights", conf_key=CONF_OPTIMISTIC_LIGHTS, device_cls=UhomeLight, user_input=user_input)`

**`async_step_pick_switches(self, user_input=None)`**
- Delegates to `_optimistic_picker_step(step_id="pick_switches", conf_key=CONF_OPTIMISTIC_SWITCHES, device_cls=UhomeSwitch, user_input=user_input)`

**`async_step_pick_locks(self, user_input=None)`**
- Delegates to `_optimistic_picker_step(step_id="pick_locks", conf_key=CONF_OPTIMISTIC_LOCKS, device_cls=UhomeLock, user_input=user_input)`

**`async_step_get_devices(self, user_input=None)`**
- Calls `self.api.discover_devices()` from `hass.data[DOMAIN][entry_id]["api"]`
- Builds `self.devices = {device["id"]: f"{name} ({category})"}` from `response["payload"]["devices"]`
- On `ValueError`: aborts with dynamic reason string
- Calls `await self.async_step_device_selection(None)`

**`async_step_device_selection(self, user_input: None)`**
- Aborts with `reason="no devices found"` if `self.devices` empty
- Current selection from `self.config_entry.options.get("devices", [])`
- Form field: `vol.Optional("selected_devices", default=current_selection): cv.multi_select(self.devices)`
- On submit: creates entry with `{"devices": user_input["selected_devices"]}`

---

## custom_components/u_tec/optimistic.py

Already 100% tested — skip per plan.

---

## custom_components/u_tec/light.py

**Module-level constants**
- `BRIGHTNESS_SCALE = (1, 100)` — U-Tec reports brightness 1-100

**`async_setup_entry(hass, entry, async_add_entities)`**
- Reads coordinator from `hass.data[DOMAIN][entry.entry_id]["coordinator"]`
- Adds `UhomeLightEntity(coordinator, device_id)` for each `device_id` where `isinstance(device, UhomeLight)`

**Class: `UhomeLightEntity(CoordinatorEntity, LightEntity)`**

Class-level defaults:
- `_optimistic_is_on: bool | None = None`
- `_optimistic_brightness: int | None = None`
- `_pending_brightness_utec: int | None = None`

```python
def __init__(self, coordinator: UhomeDataUpdateCoordinator, device_id: str) -> None
```
Sets in `__init__`:
- `self._device = cast(UhomeLight, coordinator.devices[device_id])`
- `self._attr_unique_id = f"{DOMAIN}_{device_id}"`
- `self._attr_name = self._device.name`
- `self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, self._device.device_id)}, name, manufacturer, model, hw_version)`
- `self._attr_has_entity_name = True`
- `self._optimistic_is_on: bool | None = None`
- `self._optimistic_brightness: int | None = None`
- `self._pending_brightness_utec: int | None = None`

**Color mode / supported_color_modes logic** (exact capability names checked):
- `has_brightness`: `"brightness" in supported_features or "st.brightness" in supported_features or "st.switchLevel" in supported_features`
- `has_color`: `"color" in supported_features or "st.colorControl" in supported_features`
- `has_color_temp`: `"color_temp" in supported_features or "st.colorTemperature" in supported_features`
- Adds `ColorMode.BRIGHTNESS` if has_brightness; `ColorMode.RGB` if has_color; `ColorMode.COLOR_TEMP` if has_color_temp
- Falls back to `ColorMode.ONOFF` if no modes detected
- Default color_mode: RGB > COLOR_TEMP > BRIGHTNESS > ONOFF

**Methods**
- `_is_optimistic(self) -> bool` — calls `is_optimistic_enabled(coordinator.config_entry.options, CONF_OPTIMISTIC_LIGHTS, device.device_id)`
- `available` property — `coordinator.last_update_success and self._device.available`
- `is_on` property — returns `_optimistic_is_on` if not None, else `self._device.is_on`
- `brightness` property — returns `_optimistic_brightness` if not None; else `value_to_brightness(BRIGHTNESS_SCALE, self._device.brightness)` (None if device brightness is None)
- `assumed_state` property — `_is_optimistic() and (_optimistic_is_on is not None or _optimistic_brightness is not None)`
- `rgb_color` property — delegates to `self._device.rgb_color`
- `color_temp_kelvin` property — delegates to `self._device.color_temp`
- `_handle_coordinator_update(self) -> None`
  - If `_optimistic_is_on is not None` and matches device: clears it; else keeps
  - If `_pending_brightness_utec is not None`: clears `_optimistic_brightness` and `_pending_brightness_utec` only when `self._device.brightness == pending`; else clears `_optimistic_brightness` unconditionally
  - Calls `super()._handle_coordinator_update()`
- `async async_turn_on(self, **kwargs: Any) -> None`
  - Maps `ATTR_BRIGHTNESS` (0-255) → `utec_brightness = max(1, int((brightness_255 / 255) * 100))`, passed as `brightness=`
  - Passes `ATTR_RGB_COLOR` → `rgb_color=`, `ATTR_COLOR_TEMP_KELVIN` → `color_temp=`
  - If optimistic: sets `_optimistic_is_on = True`; if brightness kwarg: sets `_optimistic_brightness = kwargs[ATTR_BRIGHTNESS]` and `_pending_brightness_utec = turn_on_args["brightness"]`
  - Raises `HomeAssistantError` on `DeviceError`
- `async async_turn_off(self, **kwargs: Any) -> None`
  - If optimistic: sets `_optimistic_is_on = False`
  - Raises `HomeAssistantError` on `DeviceError`
- `async async_added_to_hass(self)`
  - Connects `async_dispatcher_connect(hass, f"{SIGNAL_DEVICE_UPDATE}_{device.device_id}", self._handle_push_update)`
- `_handle_push_update(self, push_data) -> None` (`@callback`) — calls `self.async_write_ha_state()`

---

## custom_components/u_tec/switch.py

**Class: `UhomeSwitchEntity(CoordinatorEntity, SwitchEntity)`**

Class-level defaults:
- `_optimistic_is_on: bool | None = None`

```python
def __init__(self, coordinator: UhomeDataUpdateCoordinator, device_id: str) -> None
```
Sets:
- `self._device = cast(UhomeSwitch, coordinator.devices[device_id])`
- `self._attr_unique_id = f"{DOMAIN}_{device_id}"`
- `self._attr_name = self._device.name`
- `self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, self._device.device_id)}, name, manufacturer, model, hw_version)`
- `self._attr_has_entity_name = True`
- `self._optimistic_is_on: bool | None = None`

**Methods** (parallel shape to light, no brightness/color)
- `_is_optimistic(self) -> bool` — `is_optimistic_enabled(options, CONF_OPTIMISTIC_SWITCHES, device.device_id)`
- `available` property — `coordinator.last_update_success and self._device.available`
- `is_on` property — `_optimistic_is_on if not None else self._device.is_on`
- `assumed_state` property — `_is_optimistic() and _optimistic_is_on is not None`
- `_handle_coordinator_update(self) -> None` — clears `_optimistic_is_on` when device matches; calls `super()`
- `async async_turn_on(self, **kwargs: Any) -> None` — sets `_optimistic_is_on = True` if optimistic; raises `HomeAssistantError` on `DeviceError`
- `async async_turn_off(self, **kwargs: Any) -> None` — sets `_optimistic_is_on = False` if optimistic; raises `HomeAssistantError` on `DeviceError`
- `async async_added_to_hass(self)` — connects `f"{SIGNAL_DEVICE_UPDATE}_{device.device_id}"` → `_handle_push_update`
- `_handle_push_update(self, push_data)` (`@callback`) — calls `self.async_write_ha_state()`

**`async_setup_entry`**: adds `UhomeSwitchEntity` for each `isinstance(device, UhomeSwitch)` device

---

## custom_components/u_tec/lock.py

**Class: `UhomeLockEntity(CoordinatorEntity, LockEntity)`**

Class-level defaults:
- `_optimistic_is_locked: bool | None = None`

```python
def __init__(self, coordinator: UhomeDataUpdateCoordinator, device_id: str) -> None
```
Sets:
- `self._device = cast(UhomeLock, coordinator.devices[device_id])`
- `self._attr_unique_id = f"{DOMAIN}_{device_id}"`
- `self._attr_name = self._device.name`
- `self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, self._device.device_id)}, name, manufacturer, model, hw_version)`
- `self._attr_has_entity_name = True`
- `self._optimistic_is_locked: bool | None = None`

**Methods**
- `_is_optimistic(self) -> bool` — `is_optimistic_enabled(options, CONF_OPTIMISTIC_LOCKS, device.device_id)`
- `available` property — `coordinator.last_update_success and self._device.available`
- `is_locked` property — `_optimistic_is_locked if not None else self._device.is_locked`
- `is_jammed` property — delegates to `self._device.is_jammed`
- `assumed_state` property — `_is_optimistic() and _optimistic_is_locked is not None`
- `extra_state_attributes` property — **exact attribute keys**:
  - Always present: `"lock_state"`, `"lock_mode"`, `"battery_level"`, `"battery_status"`
  - Present only if `self._device.has_door_sensor`: `"door_state"`, `"is_door_open"`
- `_handle_coordinator_update(self) -> None`
  - Clears `_optimistic_is_locked` when `(optimistic and device.is_locked) or (not optimistic and not device.is_locked)`
  - Calls `super()`
- `async async_lock(self, **kwargs: Any) -> None` — sets `_optimistic_is_locked = True` if optimistic; raises `HomeAssistantError` on `DeviceError`
- `async async_unlock(self, **kwargs: Any) -> None` — sets `_optimistic_is_locked = False` if optimistic; raises `HomeAssistantError` on `DeviceError`
- `async async_added_to_hass(self)` — connects `f"{SIGNAL_DEVICE_UPDATE}_{device.device_id}"` → `_handle_push_update`
- `_handle_push_update(self, push_data)` (`@callback`) — calls `self.async_write_ha_state()`

**`async_setup_entry`**: adds `UhomeLockEntity` for each `isinstance(device, UhomeLock)` device

---

## custom_components/u_tec/sensor.py

**`async_setup_entry(hass, entry, async_add_entities)`**
- Calls `_create_battery_entities(coordinator)` for initial set; registers them
- Connects `SIGNAL_NEW_DEVICE` dispatcher → `async_add_sensor_entities` callback (calls `_create_battery_entities(coordinator, add_only_new=True)`)
- Unload registered via `entry.async_on_unload(...)`

**`_create_battery_entities(coordinator, add_only_new=False) -> list`**
- Iterates `coordinator.devices.items()`
- Filter: `hasattr(device, "has_capability") and device.has_capability(DeviceCapability.BATTERY_LEVEL)`
- `add_only_new` guard: `entity_id = f"{DOMAIN}_battery_{device_id}"`; skips if already in `coordinator.added_sensor_entities`
- Adds `entity_id` to `coordinator.added_sensor_entities` after adding

**Class: `UhomeBatterySensorEntity(CoordinatorEntity, SensorEntity)`**

```python
def __init__(self, coordinator: UhomeDataUpdateCoordinator, device_id: str) -> None
```
- `self._device = cast(UhomeLock, coordinator.devices[device_id])`  *(cast to Lock — battery devices are locks)*
- `self._attr_unique_id = f"{DOMAIN}_battery_{device_id}"`
- `self._attr_name = f"{self._device.name} Battery"`
- `self._attr_device_class = SensorDeviceClass.BATTERY`
- `self._attr_state_class = SensorStateClass.MEASUREMENT`
- `self._attr_native_unit_of_measurement = PERCENTAGE`

Properties:
- `native_value` → `self._device.battery_level`
- `device_class` → `self._attr_device_class`
- `state_class` → `self._attr_state_class`

Methods:
- `async async_update(self) -> None` — calls `await self._device.update()`
- `async async_added_to_hass(self)` — connects `f"{SIGNAL_DEVICE_UPDATE}_{device.device_id}"` → `_handle_push_update`
- `_handle_push_update(self, push_data)` (`@callback`) — calls `self.async_write_ha_state()`

---

## custom_components/u_tec/binary_sensor.py

**`async_setup_entry(hass, entry, async_add_entities)`**
- Filter: `isinstance(device, UhomeLock) and device.has_door_sensor`
- Adds `UhomeDoorSensor(coordinator, device_id)` for matching devices

**Class: `UhomeDoorSensor(CoordinatorEntity, BinarySensorEntity)`**

Class-level:
- `_attr_device_class = BinarySensorDeviceClass.DOOR`

```python
def __init__(self, coordinator: UhomeDataUpdateCoordinator, device_id: str) -> None
```
- `self._device = cast(UhomeLock, coordinator.devices[device_id])`
- `self._attr_unique_id = f"{DOMAIN}_door_{device_id}"`
- `self._attr_name = f"{self._device.name} Door"`
- `self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, self._device.device_id)}, name, manufacturer, model, hw_version)`

Properties:
- `available` → `coordinator.last_update_success and self._device.available`
- `is_on` — inversion: `not self._device.is_door_closed` (open=True/on, closed=False/off); returns `None` if `is_door_closed is None`

No push-update dispatcher in binary_sensor (unlike other entities — no `async_added_to_hass` override).

---

## custom_components/u_tec/application_credentials.py

```python
async def async_get_authorization_server(hass: HomeAssistant) -> AuthorizationServer
```
Returns:
```python
AuthorizationServer(
    authorize_url=OAUTH2_AUTHORIZE,  # "https://oauth.u-tec.com/authorize"
    token_url=OAUTH2_TOKEN,          # "https://oauth.u-tec.com/token"
)
```

---

## custom_components/u_tec/diagnostics.py

```python
async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]
```

**`REDACT_KEYS`** (exact set):
```python
{
    CONF_CLIENT_ID,    # "client_id"
    CONF_CLIENT_SECRET, # "client_secret"
    "access_token",
    "refresh_token",
    "id_token",
    "token",
    "serial_number",
    "id",
}
```

**Error branches in `discover_devices` call**:
- `ConnectionError` → `{"error": f"Connection error: {err!s}"}`
- `TimeoutError` → `{"error": f"Timeout error: {err!s}"}`
- `ValueError` → `{"error": f"Value error: {err!s}"}`

**Return shape** (top-level keys):
- `"config_entry"` — `async_redact_data(entry.as_dict(), REDACT_KEYS)`
- `"coordinator_data"` — `{"last_update_success": ..., "device_count": ...}`
- `"devices"` — `async_redact_data(device_data, REDACT_KEYS)` (per-device: name, handle_type, category, manufacturer, model, hw_version, supported_capabilities, available, properties_data, state_data)
- `"discovery_data"` — `async_redact_data(discovery_data, REDACT_KEYS)`
- `"query_data"` — `async_redact_data(query_data, REDACT_KEYS)`

**Per-device query error branches** (in `query_device` loop):
- `ValueError`, `ConnectionError`, `TimeoutError` each caught separately; stored as `{"error": str(err)}`

---

## Disambiguations and plan-template divergences

1. **`async_step_update_push` vs `async_step_configure_push`**: The plan template suggested `async_step_configure_push` as a possible name. The actual method is `async_step_update_push` with `step_id="update_push"`. No `configure_push` step exists.

2. **`async_step_optimistic_updates` vs `async_step_configure_optimistic`**: Plan suggested `configure_optimistic`. Actual method is `async_step_optimistic_updates` with `step_id="optimistic_updates"`.

3. **No `async_step_configure_optimistic_lights/switches/locks`**: Plan suggested a pair of "configure" + "pick" steps per type. Actual implementation has ONE step per type: `pick_lights` / `pick_switches` / `pick_locks`. The "configure" (mode selection) is a single combined `async_step_optimistic_updates` form with three dropdowns.

4. **`_advance_optimistic_picker` is NOT a step**: It is a private helper method, not called via step routing. It dispatches directly to `async_step_pick_lights/switches/locks`.

5. **`unregister_webhook` is `async`** despite plan noting it as sync: the actual method signature is `async def unregister_webhook(self) -> None`.

6. **`async_stop_periodic_discovery` is sync (not async)**: Method is `def async_stop_periodic_discovery(self) -> None` (no `async`), consistent with HA callback naming convention.

7. **`binary_sensor.py` has no push-update dispatcher**: Unlike light/switch/lock/sensor, `UhomeDoorSensor` does not override `async_added_to_hass` and does not connect to `SIGNAL_DEVICE_UPDATE`. It only refreshes via coordinator poll.

8. **diagnostics `TO_REDACT` is named `REDACT_KEYS`**: Plan template referred to it as `TO_REDACT`. The actual module-level name is `REDACT_KEYS`.

9. **`_handle_webhook` status 200**: returned as `web.json_response({"success": True})` in the `else` branch (no explicit 200 — it is the default), not as `web.Response(status=200)`.
