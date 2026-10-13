"""Tests for reported client issues."""

import hashlib
from collections.abc import Callable
from datetime import UTC, datetime

import pytest
from django.test import Client
from django.urls import reverse
from sanelib.protocol import parse_event_packet

from sanea.core.models import Computer, User


@pytest.mark.parametrize("ajax", [False, True])
def test_issues_require_management_user(
    request_client: Callable[..., Client], user_create: Callable[..., User], ajax: bool,
) -> None:
    headers = {"HTTP_HX_REQUEST": "true", "HTTP_HX_TRIGGER": "diagnostic-logs"} if ajax else {}
    anonymous_response = request_client().get(reverse("core:issues"), **headers)
    regular_response = request_client(user=user_create()).get(reverse("core:issues"), **headers)

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
    assert "sanea/js/diagnostic-logs.js" in content
    assert f"id=\"log-tab-{computer_record.pk}\"" in content
    assert "<details" not in content
    assert "every 5s [!document.hidden], diagnostic-refresh[!document.hidden]" in content
    assert ajax_response.status_code == 200
    assert "id=\"issues-content\"" in ajax_content
    assert "sanea-shell" not in ajax_content


@pytest.mark.parametrize("trigger", ["diagnostic-logs", "diagnostic-refresh"])
def test_diagnostic_refresh_returns_latest_snapshot_and_respects_filters(
    request_client: Callable[..., Client], user_create: Callable[..., User], computer_record: Computer, trigger: str,
) -> None:
    older = Computer.objects.create(
        hostname="older-computer", log_tail="older log", log_received=datetime(2026, 9, 28, tzinfo=UTC),
    )
    computer_record.replace_log_tail("original log", None)
    client = request_client(user=user_create(attributes={"is_staff": True}))
    headers = {"HTTP_HX_REQUEST": "true", "HTTP_HX_TRIGGER": trigger}

    initial = client.get(reverse("core:issues"), {"period": "all", "log": older.pk}, **headers)
    computer_record.replace_log_tail("updated <script>alert(1)</script>", None)
    refreshed = client.get(reverse("core:issues"), {"period": "7-days"}, **headers)
    selected = client.get(reverse("core:issues"), {"period": "all", "computer": older.pk}, **headers)
    initial_content = initial.content.decode()
    refreshed_content = refreshed.content.decode()
    selected_content = selected.content.decode()

    assert initial.status_code == refreshed.status_code == selected.status_code == 200
    assert f"id=\"diagnostic-computer\" name=\"log\" value=\"{older.pk}\"" in initial_content
    assert "original log" in initial_content
    assert "older log" in initial_content
    assert "updated &lt;script&gt;alert(1)&lt;/script&gt;" in refreshed_content
    assert "updated <script>" not in refreshed_content
    assert "original log" not in refreshed_content
    assert "older-computer" not in refreshed_content
    assert "older log" in selected_content
    assert "updated" not in selected_content
    assert "id=\"diagnostic-logs\"" in refreshed_content
    assert "hx-swap-oob=\"innerHTML\"" in refreshed_content
    assert "id=\"issues-content\"" not in refreshed_content
    assert "sanea-shell" not in refreshed_content


def test_log_tabs_have_native_links_with_default_period_and_invalid_selection_falls_back(
    request_client: Callable[..., Client], user_create: Callable[..., User], computer_record: Computer,
) -> None:
    computer_record.replace_log_tail("synthetic log", None)
    client = request_client(user=user_create(attributes={"is_staff": True}))

    response = client.get(reverse("core:issues"))
    fallback = client.get(reverse("core:issues"), {"period": "all", "log": "missing"})
    content = response.content.decode()

    assert response.status_code == fallback.status_code == 200
    assert f"?log={computer_record.pk}&amp;period=7-days#diagnostic-logs" in content
    assert f"id=\"diagnostic-computer\" name=\"log\" value=\"{computer_record.pk}\"" in fallback.content.decode()


@pytest.mark.parametrize("invalid", [False, True])
def test_diagnostic_refresh_handles_empty_logs_and_invalid_filters(
    request_client: Callable[..., Client], user_create: Callable[..., User], invalid: bool,
) -> None:
    client = request_client(user=user_create(attributes={"is_staff": True}))
    data = {"period": "invalid" if invalid else "7-days"}

    response = client.get(
        reverse("core:issues"), data, HTTP_HX_REQUEST="true", HTTP_HX_TRIGGER="diagnostic-logs",
    )
    content = response.content.decode()

    assert response.status_code == 200
    assert "Correct the filters" in content if invalid else "No diagnostic logs" in content
    assert "id=\"diagnostic-logs\"" in content
    assert "id=\"diagnostic-log-count\" hx-swap-oob=\"innerHTML\">0" in content
