"""Tests for the authenticated sanex control endpoint."""

import json
from copy import deepcopy
from typing import Any
from collections.abc import Callable

from django.urls import reverse
from django.utils import timezone
from time_machine import TimeMachineFixture
import pytest
from sanelib.protocol import UpdateCommandPayload
from django.http import HttpResponse
from django.test import Client

from sanea.core.client import VERIFIED_CERTIFICATE_FINGERPRINT_META
from sanea.core.models import Account, ClientCommand, CommandStatus, ComputerConfig, GlobalUpdate, Computer


SYNC_URL = reverse("core:client_sync")


def _post_sync(client: Client, computer: Computer, payload: dict[str, Any], **extra: object) -> HttpResponse:
    request_extra = {
        VERIFIED_CERTIFICATE_FINGERPRINT_META: computer.certificate_fingerprint,
        "REMOTE_ADDR": "192.168.1.77",
        **extra,
    }
    return client.post(
        SYNC_URL,
        json.dumps(payload),
        content_type="application/json",
        **request_extra,
    )


def test_sync_requires_private_verified_certificate_identity(
    request_client: Callable[..., Client],
    computer_record: Computer,
    client_sync_payload: dict[str, Any],
) -> None:
    client = request_client()
    payload = client_sync_payload["request"]

    missing = client.post(
        SYNC_URL,
        json.dumps(payload),
        content_type="application/json",
    )
    forged_header = client.post(
        SYNC_URL,
        json.dumps(payload),
        content_type="application/json",
        HTTP_X_CLIENT_CERTIFICATE_FINGERPRINT=computer_record.certificate_fingerprint,
    )

    assert missing.status_code == 403
    assert forged_header.status_code == 403
    assert ComputerConfig.objects.count() == 0


def test_sync_rejects_blocked_computer(
    request_client: Callable[..., Client],
    computer_record: Computer,
    client_sync_payload: dict[str, Any],
) -> None:
    computer_record.status = "blocked"
    computer_record.save(update_fields=("status", "updated"))

    response = _post_sync(
        request_client(),
        computer_record,
        client_sync_payload["request"],
    )

    assert response.status_code == 403
    assert ComputerConfig.objects.count() == 0


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("accounts", None),
        ("unexpected", True),
        ("config_ident", -1),
    ],
)
def test_sync_rejects_invalid_request(
    request_client: Callable[..., Client],
    computer_record: Computer,
    client_sync_payload: dict[str, Any],
    field: str,
    value: object,
) -> None:
    payload = deepcopy(client_sync_payload["request"])
    payload[field] = value

    response = _post_sync(request_client(), computer_record, payload)

    assert response.status_code == 422
    assert ComputerConfig.objects.count() == 0


def test_sync_updates_computer_and_complete_account_snapshot(
    request_client: Callable[..., Client],
    computer_record: Computer,
    client_sync_payload: dict[str, Any],
) -> None:
    existing = computer_record.accounts.get(uid=1001)
    stale = Account.objects.create(
        computer=computer_record,
        uid=1003,
        login="old",
        name="Old account",
        collect=True,
    )

    response = _post_sync(
        request_client(),
        computer_record,
        client_sync_payload["request"],
    )
    body = response.json()
    computer_record.refresh_from_db()
    existing.refresh_from_db()
    stale.refresh_from_db()
    created = computer_record.accounts.get(uid=1002)

    assert response.status_code == 200
    assert computer_record.hostname == "child-laptop"
    assert computer_record.version == "0.2.0"
    assert computer_record.last_ip == "192.168.1.77"
    assert computer_record.last_seen is not None
    assert existing.login == "child"
    assert existing.name == "Alex"
    assert existing.collect is True
    assert existing.present is True
    assert created.collect is False
    assert created.apply is False
    assert created.present is True
    assert stale.present is False
    assert body["config"]["ident"] == computer_record.current_config_id
    assert [account["uid"] for account in body["config"]["accounts"]] == [
        1001,
        1002,
        1003,
    ]
    assert body["commands"] == []


def test_sync_omitted_accounts_keeps_registry_and_matching_config_is_not_sent(
    request_client: Callable[..., Client],
    computer_record: Computer,
    client_sync_payload: dict[str, Any],
) -> None:
    client = request_client()
    payload = deepcopy(client_sync_payload["request"])
    payload.pop("accounts")

    first = _post_sync(client, computer_record, payload)
    config_ident = first.json()["config"]["ident"]
    payload["config_ident"] = config_ident
    second = _post_sync(client, computer_record, payload)
    computer_record.refresh_from_db()

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json() == {"config": None, "commands": []}
    assert computer_record.accounts.get().present is True
    assert computer_record.applied_config_id == config_ident
    assert computer_record.get_config_delivery_status() == "applied"
    assert ComputerConfig.objects.count() == 1


def test_sync_delivers_commands_and_idempotently_accepts_result(
    request_client: Callable[..., Client],
    computer_record: Computer,
    client_sync_payload: dict[str, Any],
    time_machine: TimeMachineFixture,
) -> None:
    command = ClientCommand.objects.create(
        computer=computer_record,
        type="update",
        payload={
            "version": "0.3.0",
            "index_url": "https://packages.example.test/simple",
        },
    )
    client = request_client()
    payload = deepcopy(client_sync_payload["request"])
    payload.pop("accounts")

    pending_response = _post_sync(client, computer_record, payload)
    payload["config_ident"] = pending_response.json()["config"]["ident"]
    payload["command_results"] = [
        {"ident": command.pk, "status": "done", "error": None}
    ]
    completed_at = timezone.now()
    completed_response = _post_sync(client, computer_record, payload)
    time_machine.shift(30)
    repeated_response = _post_sync(client, computer_record, payload)
    command.refresh_from_db()

    assert pending_response.json()["commands"] == [
        {
            "ident": command.pk,
            "type": "update",
            "payload": command.payload,
        }
    ]
    assert completed_response.status_code == 200
    assert completed_response.json() == {"config": None, "commands": []}
    assert repeated_response.status_code == 200
    assert command.status == CommandStatus.DONE
    assert command.error is None
    assert command.completed == completed_at


def test_sync_joins_computer_to_active_global_update(
    request_client: Callable[..., Client],
    computer_record: Computer,
    client_sync_payload: dict[str, Any],
    updates_payload: dict[str, Any],
) -> None:
    computer_record.status = "blocked"
    computer_record.save(update_fields=("status", "updated"))
    update = GlobalUpdate.activate(
        UpdateCommandPayload.model_validate(updates_payload["valid"])
    ).update
    computer_record.status = "allowed"
    computer_record.save(update_fields=("status", "updated"))
    payload = deepcopy(client_sync_payload["request"])
    payload.pop("accounts")

    response = _post_sync(request_client(), computer_record, payload)
    command = ClientCommand.objects.get(
        computer=computer_record,
        global_update=update,
    )

    assert response.status_code == 200
    assert response.json()["commands"] == [
        {
            "ident": command.pk,
            "type": "update",
            "payload": updates_payload["valid"],
        }
    ]

    payload["version"] = updates_payload["valid"]["version"]
    payload["command_results"] = [
        {"ident": command.pk, "status": "done", "error": None}
    ]
    completed = _post_sync(request_client(), computer_record, payload)
    payload["version"] = "0.2.0"
    payload["command_results"] = []
    downgraded = _post_sync(request_client(), computer_record, payload)

    assert completed.json()["commands"] == []
    assert len(downgraded.json()["commands"]) == 1
    assert downgraded.json()["commands"][0]["ident"] != command.pk


def test_sync_rejects_unknown_command_result_without_partial_update(
    request_client: Callable[..., Client],
    computer_record: Computer,
    client_sync_payload: dict[str, Any],
) -> None:
    original_hostname = computer_record.hostname
    payload = deepcopy(client_sync_payload["request"])
    payload.pop("accounts")
    payload["command_results"] = [
        {"ident": 999999, "status": "failed", "error": "unknown"}
    ]

    response = _post_sync(request_client(), computer_record, payload)
    computer_record.refresh_from_db()

    assert response.status_code == 422
    assert computer_record.hostname == original_hostname
    assert computer_record.last_ip == "192.168.1.42"
    assert ComputerConfig.objects.count() == 0


def test_sync_rejects_unrecognized_config_ident(
    request_client: Callable[..., Client],
    computer_record: Computer,
    client_sync_payload: dict[str, Any],
) -> None:
    payload = deepcopy(client_sync_payload["request"])
    payload.pop("accounts")
    payload["config_ident"] = 999999

    response = _post_sync(request_client(), computer_record, payload)
    computer_record.refresh_from_db()

    assert response.status_code == 422
    assert computer_record.applied_config_id is None
    assert computer_record.last_ip == "192.168.1.42"
    assert ComputerConfig.objects.count() == 0
