"""Configure pytest-djangoapp for the complete sanea project."""

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from django.core.management import call_command
from django.test import override_settings
from pytest_djangoapp import configure_djangoapp_plugin


os.environ["PYTHON_ENV"] = "testing"

pytest_plugins = configure_djangoapp_plugin(
    settings="sanea.settings",
    app_name="core",
)


@pytest.fixture(scope="session", autouse=True)
def collected_static(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Path]:
    static_root = tmp_path_factory.mktemp("sanea-static")

    with override_settings(STATIC_ROOT=static_root):
        call_command("collectstatic", interactive=False, verbosity=0)
        yield static_root
