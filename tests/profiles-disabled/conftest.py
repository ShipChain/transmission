import pytest


@pytest.fixture(autouse=True)
def profiles_not_enabled_settings(settings):
    settings.IOT_THING_INTEGRATION = False
    settings.PROFILES_ENABLED = False
    settings.PROFILES_URL = "DISABLED"
