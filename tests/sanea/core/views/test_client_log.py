"""Tests for authenticated sanex technical-log uploads."""

from collections.abc import Callable

from django.urls import reverse
import pytest
from django.http import HttpResponse
from django.test import Client
from sanelib.protocol import MAX_LOG_TAIL_SIZE

from sanea.core.client import VERIFIED_CERTIFICATE_FINGERPRINT_META
from sanea.core.models import Computer


LOG_URL = reverse("core:client_log")


def _put_log(client: Client, computer: Computer, content: bytes, **extra: object) -> HttpResponse:
    request_extra = {
        VERIFIED_CERTIFICATE_FINGERPRINT_META: computer.certificate_fingerprint,
        "REMOTE_ADDR": "192.168.1.78",
        **extra,
    }
    return client.put(
        LOG_URL,
        content,
        content_type="text/plain; charset=utf-8",
        **request_extra,
    )


def test_log_requires_private_verified_certificate_identity(
    request_client: Callable[..., Client],
    computer_record: Computer,
) -> None:
    client = request_client()

    missing = client.put(
        LOG_URL,
        b"missing identity\n",
        content_type="text/plain; charset=utf-8",
    )
    forged_header = client.put(
        LOG_URL,
        b"forged identity\n",
        content_type="text/plain; charset=utf-8",
        HTTP_X_CLIENT_CERTIFICATE_FINGERPRINT=(
            computer_record.certificate_fingerprint
        ),
    )
    computer_record.refresh_from_db()

    assert missing.status_code == 403
    assert forged_header.status_code == 403
    assert computer_record.log_tail == ""
    assert computer_record.log_received is None


def test_log_rejects_blocked_computer(request_client: Callable[..., Client], computer_record: Computer) -> None:
    computer_record.status = "blocked"
    computer_record.save(update_fields=("status", "updated"))

    response = _put_log(request_client(), computer_record, b"blocked\n")
    computer_record.refresh_from_db()

    assert response.status_code == 403
    assert computer_record.log_tail == ""
    assert computer_record.log_received is None


@pytest.mark.parametrize(
    ("content", "content_type", "status"),
    [
        (b"not text", "application/octet-stream", 422),
        (b"invalid UTF-8: \xff", "text/plain; charset=utf-8", 422),
        (b"x" * (MAX_LOG_TAIL_SIZE + 1), "text/plain; charset=utf-8", 413),
    ],
)
def test_log_rejects_invalid_payload(
    request_client: Callable[..., Client],
    computer_record: Computer,
    content: bytes,
    content_type: str,
    status: int,
) -> None:
    response = request_client().put(
        LOG_URL,
        content,
        content_type=content_type,
        **{
            VERIFIED_CERTIFICATE_FINGERPRINT_META: (
                computer_record.certificate_fingerprint
            )
        },
    )
    computer_record.refresh_from_db()

    assert response.status_code == status
    assert computer_record.log_tail == ""
    assert computer_record.log_received is None


def test_log_atomically_replaces_previous_snapshot(
    request_client: Callable[..., Client],
    computer_record: Computer,
) -> None:
    client = request_client()
    first = _put_log(client, computer_record, "первая\n".encode())
    computer_record.refresh_from_db()
    first_received = computer_record.log_received

    second_content = b"x" * MAX_LOG_TAIL_SIZE
    second = _put_log(client, computer_record, second_content)
    computer_record.refresh_from_db()

    assert first.status_code == 204
    assert second.status_code == 204
    assert computer_record.log_tail == second_content.decode()
    assert "первая" not in computer_record.log_tail
    assert computer_record.log_received is not None
    assert computer_record.log_received >= first_received
    assert computer_record.last_seen == computer_record.log_received
    assert computer_record.last_ip == "192.168.1.78"
