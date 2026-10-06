"""Tests for the embedded-server management command."""

import logging
from pathlib import Path
from types import SimpleNamespace
from collections.abc import Callable
from wsgiref.types import WSGIApplication

import pytest
from pytest_djangoapp.fixtures.settings import SettingsProxy

from sanea.core.management.commands import serve


def test_serve_uses_runtime_settings(
    command_run: Callable[..., str | None],
    monkeypatch: pytest.MonkeyPatch,
    settings: SettingsProxy,
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    listeners = (object(), object(), object())
    captured = {}

    def create_servers(
        application: WSGIApplication,
        host: str,
        http_port: int,
        https_port: int,
        discovery_port: int,
        pki_dir: Path,
        registration_available: Callable[[], bool],
    ) -> tuple[object, object, object]:
        captured["values"] = (
            host,
            http_port,
            https_port,
            discovery_port,
            pki_dir,
            registration_available,
        )
        return listeners

    class Runner:
        def __init__(self, servers: tuple[object, ...]) -> None:
            assert servers is listeners

        def request_stop(self) -> None:
            pass

        def run(self) -> None:
            pass

    monkeypatch.setattr(serve, "create_servers", create_servers)
    monkeypatch.setattr(serve, "ServerRunner", Runner)
    monkeypatch.setattr(
        serve.registration_window,
        "open",
        lambda: SimpleNamespace(code="ABCD-EFGH"),
    )
    settings.SERVER_HOST = "127.0.0.1"
    settings.HTTP_PORT = 18000
    settings.HTTPS_PORT = 18443
    settings.DISCOVERY_PORT = 62_117
    settings.PKI_DIR = Path("test-pki")

    with caplog.at_level(logging.INFO, logger=serve.__name__):
        command_run("serve", args=["--open-registration"])

    output = capsys.readouterr().out
    assert captured["values"] == (
        "127.0.0.1",
        18000,
        18443,
        62_117,
        Path("test-pki"),
        serve.is_registration_discovery_available,
    )
    assert "HTTP listening on 127.0.0.1:18000" in caplog.text
    assert "HTTPS listening on 127.0.0.1:18443" in caplog.text
    assert "UDP discovery on 127.0.0.1:62117" in caplog.text
    assert "CA certificate: test-pki/ca.crt" in caplog.text
    assert output == "SANEA_REGISTRATION_CODE=ABCD-EFGH\n"
    assert "ABCD-EFGH" not in caplog.text
    assert "SANEA_REGISTRATION_CODE" not in caplog.text
