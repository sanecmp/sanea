"""Tests for envbox-backed Django settings."""

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from django.conf import settings


def test_testing_environment_defaults(settings_payload: dict[str, Any]) -> None:
    assert f"{settings.ENVIRONMENT}" == settings_payload["environment"]
    assert settings.STATE_DIR == Path(settings_payload["state_dir"])
    assert settings.DATABASE_PATH == Path(settings_payload["database_path"])
    assert settings.ALLOWED_HOSTS == settings_payload["allowed_hosts"]
    assert settings.DISCOVERY_PORT == 62_117
    assert settings.DEBUG is settings_payload["debug"]
    assert settings.SESSION_COOKIE_SECURE is settings_payload["session_cookie_secure"]


def test_environment_specific_module_is_loaded() -> None:
    assert settings.LANGUAGE_CODE == "en"
    assert settings.LANGUAGES == [("en", "English"), ("ru", "Russian")]
    assert settings.MIDDLEWARE.index(
        "django.middleware.locale.LocaleMiddleware"
    ) == settings.MIDDLEWARE.index(
        "django.contrib.sessions.middleware.SessionMiddleware"
    ) + 1
    assert settings.PASSWORD_HASHERS == ["django.contrib.auth.hashers.MD5PasswordHasher"]


def test_development_module_is_selected_in_subprocess(tmp_path: Path) -> None:
    environment = _clean_environment()
    environment["PYTHON_ENV"] = "development"

    result = _read_settings(environment, tmp_path)

    assert result == {
        "environment": "development",
        "debug": True,
        "session_cookie_secure": False,
        "state_dir": ".state",
        "database_path": ".state/sanea.sqlite3",
        "discovery_port": 62_117,
        "allowed_hosts": ["localhost", "127.0.0.1", "0.0.0.0", "[::1]"],
    }


def test_production_is_the_safe_default(tmp_path: Path) -> None:
    environment = _clean_environment()
    environment["SANEA_SECRET_KEY"] = "production-test-secret"

    result = _read_settings(environment, tmp_path)

    assert result == {
        "environment": "production",
        "debug": False,
        "session_cookie_secure": True,
        "state_dir": "/opt/sanea/state",
        "database_path": "/opt/sanea/state/sanea.sqlite3",
        "discovery_port": 62_117,
        "allowed_hosts": ["localhost", "127.0.0.1", "[::1]"],
    }


def test_testing_defaults_do_not_require_envfile(tmp_path: Path) -> None:
    environment = _clean_environment()
    environment["PYTHON_ENV"] = "testing"

    result = _read_settings(environment, tmp_path)

    assert result == {
        "environment": "testing",
        "debug": False,
        "session_cookie_secure": False,
        "state_dir": "/tmp/sanea-tests",
        "database_path": ":memory:",
        "discovery_port": 62_117,
        "allowed_hosts": ["localhost", "127.0.0.1", "testserver"],
    }


@pytest.mark.parametrize("environment_name", ["development", "testing"])
def test_local_envfile_and_environment_override_defaults(
    tmp_path: Path,
    environment_name: str,
) -> None:
    (tmp_path / f".env.{environment_name}").write_text(
        "SANEA_STATE_DIR=envfile-state\n"
        "SANEA_DATABASE_PATH=custom.sqlite3\n"
        "SANEA_ALLOWED_HOSTS=[\"custom.home\"]\n"
        "SANEA_DISCOVERY_PORT=62118\n"
    )
    environment = _clean_environment()
    environment["PYTHON_ENV"] = environment_name
    environment["SANEA_STATE_DIR"] = "environment-state"

    result = _read_settings(environment, tmp_path)

    assert result["state_dir"] == "environment-state"
    assert result["database_path"] == "custom.sqlite3"
    assert result["allowed_hosts"] == ["custom.home"]
    assert result["discovery_port"] == 62_118


def test_production_requires_secret_key(tmp_path: Path) -> None:
    result = subprocess.run(
        [sys.executable, "-c", "import sanea.settings"],
        cwd=tmp_path,
        env=_clean_environment(),
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert "SANEA_SECRET_KEY is required" in result.stderr


def _clean_environment() -> dict[str, str]:
    return {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("SANEA_") and key != "PYTHON_ENV"
    }


def _read_settings(environment: dict[str, str], cwd: Path) -> dict[str, Any]:
    output = subprocess.check_output(
        [
            sys.executable,
            "-c",
            (
                "import json; from sanea import settings; "
                "print(json.dumps({'environment': f'{settings.ENVIRONMENT}', "
                "'debug': settings.DEBUG, "
                "'session_cookie_secure': settings.SESSION_COOKIE_SECURE, "
                "'state_dir': f'{settings.STATE_DIR}', "
                "'database_path': f'{settings.DATABASE_PATH}', "
                "'discovery_port': settings.DISCOVERY_PORT, "
                "'allowed_hosts': settings.ALLOWED_HOSTS}))"
            ),
        ],
        cwd=cwd,
        env=environment,
        text=True,
    )
    return json.loads(output)
