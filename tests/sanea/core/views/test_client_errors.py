"""Tests for shared sanex endpoint failure handling."""

import json
import logging
from importlib import import_module
from typing import Any, Never
from collections.abc import Callable

from django.urls import reverse
from django.db import DatabaseError
import pytest
from django.http import HttpRequest, HttpResponse
from django.test import Client
from pytest_djangoapp.fixtures.settings import SettingsProxy
from sanelib.protocol import SyncRequest

from sanea.core.client import VERIFIED_CERTIFICATE_FINGERPRINT_META
from sanea.core.models import Computer


SYNC_URL = reverse("core:client_sync")


def post_sync(client: Client, computer: Computer, payload: dict[str, Any]) -> HttpResponse:
    """Submit one authenticated synchronization request."""
    return client.post(
        SYNC_URL,
        json.dumps(payload),
        content_type="application/json",
        **{
            VERIFIED_CERTIFICATE_FINGERPRINT_META: (
                computer.certificate_fingerprint
            )
        },
    )


def test_request_body_limit_returns_empty_413(
    request_client: Callable[..., Client],
    computer_record: Computer,
    client_sync_payload: dict[str, Any],
    settings: SettingsProxy,
) -> None:

    with settings(DATA_UPLOAD_MAX_MEMORY_SIZE=16):
        response = post_sync(
            request_client(),
            computer_record,
            client_sync_payload["request"],
        )

    assert response.status_code == 413
    assert response.content == b""


def test_database_failure_returns_empty_503_and_is_logged(
    request_client: Callable[..., Client],
    computer_record: Computer,
    client_sync_payload: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    client_views = import_module("sanea.core.views.client")

    def fail_authentication(request: HttpRequest) -> Never:
        raise DatabaseError("database unavailable")

    monkeypatch.setattr(
        client_views,
        "computer_from_verified_certificate",
        fail_authentication,
    )

    with caplog.at_level(logging.ERROR):
        response = post_sync(
            request_client(),
            computer_record,
            client_sync_payload["request"],
        )

    assert response.status_code == 503
    assert response.content == b""
    assert "Unable to synchronize sanex client" in caplog.text
    record = next(record for record in caplog.records if record.name == client_views.__name__)
    assert record.msg == "Unable to %s"
    assert record.args == ("synchronize sanex client",)
    assert record.exc_info is not None


def test_unexpected_failure_uses_generic_500_without_leaking_detail(
    request_client: Callable[..., Client],
    computer_record: Computer,
    client_sync_payload: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client_views = import_module("sanea.core.views.client")

    def fail_synchronization(computer: Computer, request: SyncRequest, remote_ip: str | None) -> Never:
        raise RuntimeError("private implementation detail")

    monkeypatch.setattr(client_views, "synchronize_client", fail_synchronization)
    client = request_client()
    client.raise_request_exception = False

    response = post_sync(
        client,
        computer_record,
        client_sync_payload["request"],
    )

    assert response.status_code == 500
    assert b"private implementation detail" not in response.content
