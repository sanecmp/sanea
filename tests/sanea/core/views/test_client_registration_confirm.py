"""Tests for authenticated completion of sanex registration."""

import json
from copy import deepcopy
from typing import Any
from collections.abc import Callable

from django.urls import reverse
import pytest
from django.http import HttpResponse
from django.test import Client

from sanea.core.client import VERIFIED_CERTIFICATE_FINGERPRINT_META
from sanea.core.models import Account, Computer, ComputerConfig, ComputerStatus
from sanea.exceptions import ComputerConfigError


CONFIRM_URL = reverse("core:client_register_confirm")


@pytest.fixture
def pending_computer(
    client_registration_confirm_payload: dict[str, Any],
) -> Computer:
    """Create the pending computer represented by the confirmation fixture."""
    return Computer.objects.create(
        **client_registration_confirm_payload["computer"],
    )


def _post_confirm(client: Client, computer: Computer, payload: dict[str, Any], **extra: object) -> HttpResponse:
    request_extra = {
        VERIFIED_CERTIFICATE_FINGERPRINT_META: computer.certificate_fingerprint,
        "REMOTE_ADDR": "192.168.1.88",
        **extra,
    }
    return client.post(
        CONFIRM_URL,
        json.dumps(payload),
        content_type="application/json",
        **request_extra,
    )


def test_confirm_requires_private_verified_certificate_identity(
    request_client: Callable[..., Client],
    pending_computer: Computer,
    client_registration_confirm_payload: dict[str, Any],
) -> None:
    client = request_client()
    payload = client_registration_confirm_payload["request"]

    missing = client.post(
        CONFIRM_URL,
        json.dumps(payload),
        content_type="application/json",
    )
    forged_header = client.post(
        CONFIRM_URL,
        json.dumps(payload),
        content_type="application/json",
        HTTP_X_CLIENT_CERTIFICATE_FINGERPRINT=(
            pending_computer.certificate_fingerprint
        ),
    )
    pending_computer.refresh_from_db()

    assert missing.status_code == 403
    assert forged_header.status_code == 403
    assert pending_computer.status == ComputerStatus.PENDING
    assert ComputerConfig.objects.count() == 0


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("accounts", None),
        ("unexpected", True),
        ("version", ""),
        (
            "accounts",
            [
                {"uid": 1001, "login": "child", "name": "Alex"},
                {"uid": 1001, "login": "child-2", "name": "Alex 2"},
            ],
        ),
    ],
)
def test_confirm_rejects_invalid_request_without_partial_changes(
    request_client: Callable[..., Client],
    pending_computer: Computer,
    client_registration_confirm_payload: dict[str, Any],
    field: str,
    value: object,
) -> None:
    payload = deepcopy(client_registration_confirm_payload["request"])
    payload[field] = value

    response = _post_confirm(request_client(), pending_computer, payload)
    pending_computer.refresh_from_db()

    assert response.status_code == 422
    assert pending_computer.status == ComputerStatus.PENDING
    assert pending_computer.version == ""
    assert Account.objects.count() == 0
    assert ComputerConfig.objects.count() == 0


def test_confirm_rejects_blocked_computer(
    request_client: Callable[..., Client],
    pending_computer: Computer,
    client_registration_confirm_payload: dict[str, Any],
) -> None:
    pending_computer.status = ComputerStatus.BLOCKED
    pending_computer.save(update_fields=("status", "updated"))

    response = _post_confirm(
        request_client(),
        pending_computer,
        client_registration_confirm_payload["request"],
    )

    assert response.status_code == 403
    assert Account.objects.count() == 0
    assert ComputerConfig.objects.count() == 0


def test_confirm_allows_client_and_returns_idempotent_initial_config(
    request_client: Callable[..., Client],
    pending_computer: Computer,
    client_registration_confirm_payload: dict[str, Any],
) -> None:
    client = request_client()
    payload = client_registration_confirm_payload["request"]

    response = _post_confirm(client, pending_computer, payload)
    repeated = _post_confirm(client, pending_computer, payload)
    pending_computer.refresh_from_db()
    accounts = list(pending_computer.accounts.order_by("uid"))

    assert response.status_code == 200
    assert response.json() == repeated.json()
    assert pending_computer.status == ComputerStatus.ALLOWED
    assert pending_computer.version == payload["version"]
    assert pending_computer.last_ip == "192.168.1.88"
    assert pending_computer.last_seen is not None
    assert len(accounts) == 2
    assert [(account.uid, account.login, account.name) for account in accounts] == [
        (1001, "child", "Alex"),
        (1002, "guest", "Guest"),
    ]
    assert all(account.present for account in accounts)
    assert all(not account.collect and not account.apply for account in accounts)
    config = response.json()["config"]
    assert config["ident"] == pending_computer.current_config_id
    assert [account["uid"] for account in config["accounts"]] == [1001, 1002]
    assert all(account["limits"] is None for account in config["accounts"])
    assert ComputerConfig.objects.count() == 1


def test_confirm_rolls_back_when_initial_config_cannot_be_built(
    request_client: Callable[..., Client],
    pending_computer: Computer,
    client_registration_confirm_payload: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_materialization(computer: Computer) -> ComputerConfig:
        raise ComputerConfigError("test failure")

    monkeypatch.setattr(Computer, "materialize_config", fail_materialization)

    response = _post_confirm(
        request_client(),
        pending_computer,
        client_registration_confirm_payload["request"],
    )
    pending_computer.refresh_from_db()

    assert response.status_code == 503
    assert pending_computer.status == ComputerStatus.PENDING
    assert pending_computer.version == ""
    assert Account.objects.count() == 0
    assert ComputerConfig.objects.count() == 0
