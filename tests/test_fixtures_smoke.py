"""Smoke test: HA fixtures and test builders wire up."""


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
