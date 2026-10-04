"""Polling interval UI, persistence, and coordinator scheduling regressions."""

from datetime import timedelta
from types import MappingProxyType
from unittest.mock import AsyncMock, patch

import pytest
import voluptuous as vol

from custom_components.u_tec import (
    _resolve_scan_interval,
    async_setup_entry,
    async_unload_entry,
    async_update_options,
)
from custom_components.u_tec.config_flow import OptionsFlowHandler
from custom_components.u_tec.const import (
    CONF_DISCOVERY_INTERVAL,
    CONF_PUSH_ENABLED,
    CONF_SCAN_INTERVAL,
    DEFAULT_DISCOVERY_INTERVAL,
    DOMAIN,
    YAML_CONFIG_KEY,
)
from tests.common import make_config_entry
from tests.test_setup import _patched_setup_env, patched_uhomeapi  # noqa: F401


async def _polling_form(hass, entry):
    result = await hass.config_entries.options.async_init(entry.entry_id)
    return await hass.config_entries.options.async_configure(
        result["flow_id"], user_input={"next_step_id": "polling_interval"},
    )


@pytest.mark.parametrize("interval", [10, 15, 3600])
async def test_polling_save_persists_and_reopens(hass, interval):
    options = {CONF_PUSH_ENABLED: False, "devices": ["lock-1"]}
    entry = make_config_entry(options=options)
    entry.add_to_hass(hass)
    hass.data.setdefault(DOMAIN, {})[YAML_CONFIG_KEY] = {CONF_SCAN_INTERVAL: 30}

    form = await _polling_form(hass, entry)
    selector = next(iter(form["data_schema"].schema.values()))
    assert selector.config["min"] == 10
    assert selector.config["max"] == 3600
    assert selector.config["step"] == 1
    assert form["data_schema"]({CONF_SCAN_INTERVAL: interval}) == {
        CONF_SCAN_INTERVAL: interval,
    }

    result = await hass.config_entries.options.async_configure(
        form["flow_id"], user_input={CONF_SCAN_INTERVAL: interval},
    )
    assert result["type"] == "create_entry"
    assert dict(entry.options) == {**options, CONF_SCAN_INTERVAL: interval}
    assert _resolve_scan_interval(hass, entry) == interval

    reopened = await _polling_form(hass, entry)
    field = next(iter(reopened["data_schema"].schema))
    assert field.default() == interval


@pytest.mark.parametrize("options,yaml,expected", [
    ({}, {}, 20),
    ({}, {CONF_SCAN_INTERVAL: 1}, 10),
    ({CONF_SCAN_INTERVAL: 1}, {CONF_SCAN_INTERVAL: 30}, 10),
    ({}, {CONF_SCAN_INTERVAL: 0}, 10),
    ({CONF_SCAN_INTERVAL: 15}, {}, 15),
    ({CONF_SCAN_INTERVAL: 99999}, {}, 3600),
])
async def test_polling_prefill_and_startup_resolution(hass, options, yaml, expected):
    entry = make_config_entry(options=options)
    entry.add_to_hass(hass)
    hass.data.setdefault(DOMAIN, {})[YAML_CONFIG_KEY] = yaml
    form = await _polling_form(hass, entry)
    field = next(iter(form["data_schema"].schema))
    assert field.default() == expected
    assert _resolve_scan_interval(hass, entry) == expected


@pytest.mark.parametrize("interval", [-1, 0, 1, 9, 3601])
async def test_polling_rejects_out_of_range_in_selector_and_backend(hass, interval):
    entry = make_config_entry()
    entry.add_to_hass(hass)
    form = await _polling_form(hass, entry)
    with pytest.raises(vol.Invalid):
        form["data_schema"]({CONF_SCAN_INTERVAL: interval})
    handler = OptionsFlowHandler(entry)
    with pytest.raises(vol.Invalid):
        await handler.async_step_polling_interval({CONF_SCAN_INTERVAL: interval})
    assert CONF_SCAN_INTERVAL not in entry.options


@pytest.mark.parametrize(
    "interval,expected", [(1, 10), (5, 10), (10, 10), (15, 15), (0, 10), (3601, 3600)],
)
async def test_options_reschedules_and_reload_preserves_interval(
    hass, patched_uhomeapi, interval, expected,
):
    entry = make_config_entry(options={CONF_PUSH_ENABLED: False})
    entry.add_to_hass(hass)
    hass.data.setdefault(DOMAIN, {})[YAML_CONFIG_KEY] = {CONF_SCAN_INTERVAL: 30}

    with _patched_setup_env(hass), patch.object(
        hass.config_entries, "async_unload_platforms", new=AsyncMock(return_value=True),
    ):
        await async_setup_entry(hass, entry)
        coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
        assert coordinator.update_interval == timedelta(seconds=30)
        assert coordinator._discovery_interval == timedelta(seconds=DEFAULT_DISCOVERY_INTERVAL)
        object.__setattr__(entry, "options", MappingProxyType({
            CONF_PUSH_ENABLED: False, CONF_SCAN_INTERVAL: interval,
        }))
        with patch.object(coordinator, "_schedule_refresh") as schedule:
            await async_update_options(hass, entry)
        schedule.assert_called_once_with()
        assert coordinator.update_interval == timedelta(seconds=expected)
        assert coordinator._discovery_interval == timedelta(seconds=DEFAULT_DISCOVERY_INTERVAL)

        assert await async_unload_entry(hass, entry)
        assert await async_setup_entry(hass, entry)
        reloaded = hass.data[DOMAIN][entry.entry_id]["coordinator"]
        assert reloaded.update_interval == timedelta(seconds=expected)
        assert reloaded._discovery_interval == timedelta(seconds=DEFAULT_DISCOVERY_INTERVAL)


async def test_legacy_one_second_option_clamped_on_startup(hass, patched_uhomeapi, caplog):  # noqa: F811
    """A 1s value saved under v0.6.1 is raised to the floor, saved, and logged."""
    entry = make_config_entry(options={CONF_PUSH_ENABLED: False, CONF_SCAN_INTERVAL: 1})
    entry.add_to_hass(hass)
    hass.data.setdefault(DOMAIN, {})[YAML_CONFIG_KEY] = {
        CONF_SCAN_INTERVAL: 30, CONF_DISCOVERY_INTERVAL: 600,
    }
    with _patched_setup_env(hass):
        assert await async_setup_entry(hass, entry)
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    assert coordinator.update_interval == timedelta(seconds=10)
    assert coordinator._discovery_interval == timedelta(seconds=600)
    assert entry.options[CONF_SCAN_INTERVAL] == 10
    assert entry.options[CONF_PUSH_ENABLED] is False
    records = [r for r in caplog.records if "below the 10s minimum" in r.getMessage()]
    assert len(records) == 1
    assert records[0].levelname == "WARNING"


async def test_legacy_yaml_interval_clamped_and_logged(hass, patched_uhomeapi, caplog):  # noqa: F811
    """YAML cannot be rewritten, so it is clamped at runtime with a notice."""
    entry = make_config_entry(options={CONF_PUSH_ENABLED: False})
    entry.add_to_hass(hass)
    hass.data.setdefault(DOMAIN, {})[YAML_CONFIG_KEY] = {CONF_SCAN_INTERVAL: 2}
    with _patched_setup_env(hass):
        assert await async_setup_entry(hass, entry)
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    assert coordinator.update_interval == timedelta(seconds=10)
    assert CONF_SCAN_INTERVAL not in entry.options
    assert any(
        "configuration.yaml poll interval of 2s" in r.getMessage()
        for r in caplog.records
    )


async def test_interval_at_floor_is_not_rewritten_or_logged(hass, patched_uhomeapi, caplog):  # noqa: F811
    entry = make_config_entry(options={CONF_PUSH_ENABLED: False, CONF_SCAN_INTERVAL: 10})
    entry.add_to_hass(hass)
    with _patched_setup_env(hass):
        assert await async_setup_entry(hass, entry)
    assert entry.options[CONF_SCAN_INTERVAL] == 10
    assert not any("minimum" in r.getMessage() for r in caplog.records)
