"""Translations stay in sync and carry the community disclaimer."""

import json
from pathlib import Path

from custom_components.u_tec.sensor import API_STAT_SENSORS

BASE = Path(__file__).resolve().parent.parent / "custom_components" / "u_tec"
DISCLAIMER = "Not made, endorsed, or supported by U-tec or Xthings"


def _load(name):
    return json.loads((BASE / name).read_text(encoding="utf-8"))


def test_strings_and_english_translation_match():
    assert _load("strings.json") == _load("translations/en.json")


def test_disclaimer_shown_at_setup_and_in_options():
    strings = _load("strings.json")
    assert DISCLAIMER in strings["config"]["step"]["replace_credentials"]["description"]
    assert DISCLAIMER in strings["options"]["step"]["init"]["description"]


def test_polling_help_explains_shared_api():
    text = _load("strings.json")["options"]["step"]["polling_interval"]["description"]
    assert text.startswith("Minimum 10 seconds.")
    assert "shares U-tec's API, which has no published limits" in text
    assert "Adaptive Aggressive" in text


def test_every_entity_translation_key_exists():
    entity = _load("strings.json")["entity"]
    for description in API_STAT_SENSORS:
        assert description.translation_key in entity["sensor"]
    assert "device_api_commands" in entity["sensor"]
    assert set(entity["button"]) == {"start_debug_polling", "stop_debug_polling"}
    assert "debug_polling" in entity["binary_sensor"]


def test_readme_leads_with_disclaimer():
    readme = (BASE.parent.parent / "README.md").read_text(encoding="utf-8")
    first_screen = readme.split("## Community responsibility")[0]
    assert DISCLAIMER in first_screen
