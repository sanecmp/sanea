"""Tests for reported client issues."""

import hashlib
from collections.abc import Callable

from django.urls import reverse
from sanelib.protocol import parse_event_packet
from django.test import Client

from sanea.core.models import Computer, User


def test_issues_require_management_user(request_client: Callable[..., Client], user_create: Callable[..., User]) -> None:
    anonymous_response = request_client().get(reverse("core:issues"))
    regular_response = request_client(user=user_create()).get(reverse("core:issues"))

    assert anonymous_response.status_code == 302
    assert anonymous_response.url.startswith(reverse("core:sign_in"))
    assert regular_response.status_code == 403


def test_issues_show_enforcement_failures_and_escaped_log_tail(
    request_client: Callable[..., Client],
    user_create: Callable[..., User],
    computer_record: Computer,
    client_events_content: bytes,
) -> None:
    staff_user = user_create(attributes={"is_staff": True})
    account = computer_record.accounts.get()
    digest = hashlib.sha256(client_events_content).hexdigest()
    packet = parse_event_packet(client_events_content, digest)
    account.store_event_packet(packet, len(client_events_content), None)
    computer_record.replace_log_tail("failed <script>alert(1)</script>", None)
    client = request_client(user=staff_user)

    response = client.get(reverse("core:issues"), {"period": "30-days"})
    ajax_response = client.get(
        reverse("core:issues"),
        {"period": "30-days", "computer": computer_record.pk},
        HTTP_HX_REQUEST="true",
        HTTP_HX_TRIGGER="issue-filter",
    )
    content = response.content.decode()
    ajax_content = ajax_response.content.decode()

    assert response.status_code == 200
    assert "id=\"icon-issues\"" in content
    assert f"href=\"{reverse("core:issues")}\"" in content
    assert "Close unsupported" in content
    assert computer_record.name in content
    assert "UID 1001" in content
    assert "failed &lt;script&gt;alert(1)&lt;/script&gt;" in content
    assert "failed <script>" not in content
    assert ajax_response.status_code == 200
    assert "id=\"issues-content\"" in ajax_content
    assert "sanea-shell" not in ajax_content
