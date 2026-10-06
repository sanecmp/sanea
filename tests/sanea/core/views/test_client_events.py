"""Tests for authenticated sanex event-packet uploads."""

import hashlib
from collections.abc import Callable

from django.urls import reverse
import pytest
from django.http import HttpResponse
from django.test import Client
from sanelib.protocol import MAX_EVENT_PACKET_SIZE

from sanea.core.client import VERIFIED_CERTIFICATE_FINGERPRINT_META
from sanea.core.models import ActivityEvent, EventPacket, Computer


def _post_events(
    client: Client,
    computer: Computer,
    content: bytes,
    *,
    uid: int = 1001,
    digest: str | None = None,
    content_type: str = "application/x-ndjson",
) -> HttpResponse:
    packet_digest = digest or hashlib.sha256(content).hexdigest()
    return client.post(
        reverse("core:client_events", kwargs={"uid": uid, "sha256": packet_digest}),
        content,
        content_type=content_type,
        **{
            VERIFIED_CERTIFICATE_FINGERPRINT_META: (
                computer.certificate_fingerprint
            ),
            "REMOTE_ADDR": "192.168.1.79",
        },
    )


def test_events_require_private_verified_certificate_identity(
    request_client: Callable[..., Client],
    computer_record: Computer,
    client_events_content: bytes,
) -> None:
    client = request_client()
    digest = hashlib.sha256(client_events_content).hexdigest()
    url = reverse("core:client_events", kwargs={"uid": 1001, "sha256": digest})

    missing = client.post(
        url,
        client_events_content,
        content_type="application/x-ndjson",
    )
    forged_header = client.post(
        url,
        client_events_content,
        content_type="application/x-ndjson",
        HTTP_X_CLIENT_CERTIFICATE_FINGERPRINT=(
            computer_record.certificate_fingerprint
        ),
    )

    assert missing.status_code == 403
    assert forged_header.status_code == 403
    assert EventPacket.objects.count() == 0
    assert ActivityEvent.objects.count() == 0


def test_events_store_exact_packet_identity_and_typed_records(
    request_client: Callable[..., Client],
    computer_record: Computer,
    client_events_content: bytes,
) -> None:
    response = _post_events(
        request_client(),
        computer_record,
        client_events_content,
    )
    packet = EventPacket.objects.get()
    events = list(ActivityEvent.objects.order_by("seq"))
    computer_record.refresh_from_db()

    assert response.status_code == 201
    assert packet.sha256 == hashlib.sha256(client_events_content).hexdigest()
    assert packet.first_seq == 120
    assert packet.last_seq == 141
    assert packet.event_count == 5
    assert packet.byte_size == len(client_events_content)
    assert [event.type for event in events] == [
        "session_start",
        "prc_start",
        "session_end",
        "prc_end",
        "enforcement_failed",
    ]
    assert events[0].sess_ident == "3"
    assert events[1].exe == "/opt/yandex/browser/yandex_browser"
    assert events[2].duration == 3017
    assert events[4].rule_ident == 701
    assert events[4].reason == "close_unsupported"
    assert computer_record.last_ip == "192.168.1.79"
    assert computer_record.last_seen is not None


def test_events_idempotently_acknowledge_an_existing_packet(
    request_client: Callable[..., Client],
    computer_record: Computer,
    client_events_content: bytes,
) -> None:
    client = request_client()

    first = _post_events(client, computer_record, client_events_content)
    repeated = _post_events(client, computer_record, client_events_content)

    assert first.status_code == 201
    assert repeated.status_code == 204
    assert EventPacket.objects.count() == 1
    assert ActivityEvent.objects.count() == 5


@pytest.mark.parametrize(
    ("change", "expected_status"),
    [
        ("missing_account", 404),
        ("blocked", 403),
        ("disabled", 403),
        ("invalid_digest", 422),
        ("invalid_content_type", 422),
        ("too_large", 413),
    ],
)
def test_events_reject_invalid_or_disallowed_uploads(
    request_client: Callable[..., Client],
    computer_record: Computer,
    client_events_content: bytes,
    change: str,
    expected_status: int,
) -> None:
    content = client_events_content
    kwargs = {}

    if change == "missing_account":
        kwargs["uid"] = 9999

    elif change == "blocked":
        computer_record.status = "blocked"
        computer_record.save(update_fields=("status", "updated"))

    elif change == "disabled":
        account = computer_record.accounts.get(uid=1001)
        account.collect = False
        account.save(update_fields=("collect", "updated"))

    elif change == "invalid_digest":
        kwargs["digest"] = "0" * 64

    elif change == "invalid_content_type":
        kwargs["content_type"] = "application/json"

    elif change == "too_large":
        content = b"x" * (MAX_EVENT_PACKET_SIZE + 1)

    response = _post_events(
        request_client(),
        computer_record,
        content,
        **kwargs,
    )

    assert response.status_code == expected_status
    assert EventPacket.objects.count() == 0
    assert ActivityEvent.objects.count() == 0


def test_events_reject_sequence_conflict_without_partial_storage(
    request_client: Callable[..., Client],
    computer_record: Computer,
    client_events_content: bytes,
) -> None:
    client = request_client()
    first_record = client_events_content.splitlines(keepends=True)[0]

    saved = _post_events(client, computer_record, client_events_content)
    conflict = _post_events(client, computer_record, first_record)

    assert saved.status_code == 201
    assert conflict.status_code == 409
    assert EventPacket.objects.count() == 1
    assert ActivityEvent.objects.count() == 5
