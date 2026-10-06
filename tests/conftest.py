"""Configure pytest-djangoapp for the complete sanea project."""

import os

from pytest_djangoapp import configure_djangoapp_plugin


os.environ["PYTHON_ENV"] = "testing"

pytest_plugins = configure_djangoapp_plugin(
    settings="sanea.settings",
    app_name="core",
)
