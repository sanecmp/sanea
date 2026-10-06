"""Tests for Django management commands exposed by sanea."""

import logging
import os
import subprocess
import sys
from pathlib import Path
from collections.abc import Callable

from pytest import CaptureFixture, MonkeyPatch
from django.conf import settings
import pytest

from sanea.cli import main


def test_django_system_check(command_run: Callable[..., str | None], capsys: pytest.CaptureFixture[str]) -> None:
    command_run("check")

    assert "System check identified no issues" in capsys.readouterr().out


def test_exposes_django_management_commands(capsys: pytest.CaptureFixture[str]) -> None:
    main(["sanea", "help"])

    output = capsys.readouterr().out
    assert "migrate" in output
    assert "createsuperuser" in output
    assert "serve" in output


def test_creates_runtime_directories(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    state_dir = tmp_path / "state"
    database_path = tmp_path / "database" / "sanea.sqlite3"
    monkeypatch.setattr(settings, "STATE_DIR", state_dir)
    monkeypatch.setattr(settings, "DATABASE_PATH", database_path)

    main(["sanea", "help"])
    capsys.readouterr()

    assert state_dir.is_dir()
    assert database_path.parent.is_dir()


def test_wsgi_import_does_not_create_runtime_directories(tmp_path: Path) -> None:
    state_dir = tmp_path / "absent-state"
    database_dir = tmp_path / "absent-database"
    environment = {
        **os.environ,
        "PYTHON_ENV": "testing",
        "DJANGO_SETTINGS_MODULE": "sanea.settings",
        "SANEA_SECRET_KEY": "isolated-wsgi-test-key",
        "SANEA_STATE_DIR": f"{state_dir}",
        "SANEA_DATABASE_PATH": f"{database_dir / "sanea.sqlite3"}",
        "SANEA_PKI_DIR": f"{state_dir / "pki"}",
    }

    result = subprocess.run(
        [sys.executable, "-c", "import sanea.wsgi"],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert not state_dir.exists()
    assert not database_dir.exists()


def test_cli_preserves_caller_logging(
    monkeypatch: MonkeyPatch,
    capsys: CaptureFixture[str],
) -> None:
    root_logger = logging.getLogger()
    handler = logging.StreamHandler()
    formatter = logging.Formatter("caller: %(message)s")
    handler.setFormatter(formatter)
    handler.setLevel(logging.WARNING)
    monkeypatch.setattr(root_logger, "handlers", [handler])
    monkeypatch.setattr(root_logger, "level", logging.ERROR)

    main(["sanea", "help"])
    main(["sanea", "help"])
    capsys.readouterr()

    assert root_logger.handlers == [handler]
    assert root_logger.level == logging.ERROR
    assert handler.level == logging.WARNING
    assert handler.formatter is formatter


def test_cli_initializes_stderr_logging_once(
    monkeypatch: MonkeyPatch,
    capsys: CaptureFixture[str],
) -> None:
    root_logger = logging.getLogger()
    monkeypatch.setattr(root_logger, "handlers", [])
    monkeypatch.setattr(root_logger, "level", logging.WARNING)

    try:
        main(["sanea", "help"])
        handlers = tuple(root_logger.handlers)
        main(["sanea", "help"])
        logging.getLogger("sanea.cli-test").info("CLI diagnostic")
        output = capsys.readouterr()

        assert len(handlers) == 1
        assert tuple(root_logger.handlers) == handlers
        assert "CLI diagnostic" in output.err
        assert "CLI diagnostic" not in output.out

    finally:

        for handler in root_logger.handlers:
            handler.close()
