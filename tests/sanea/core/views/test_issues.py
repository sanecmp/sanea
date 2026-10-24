"""Tests for reported client issues."""

import hashlib
from collections.abc import Callable
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest
from django.test import Client
from django.urls import reverse
from django.utils import timezone
from django.utils.formats import date_format
from sanelib.protocol import parse_event_packet

from sanea.core.models import ActivityEvent, Computer, EventPacket, User


@pytest.mark.parametrize("ajax", [False, True])
def test_issues_require_management_user(
    request_client: Callable[..., Client], user_create: Callable[..., User], ajax: bool,
) -> None:
    headers = {"HTTP_HX_REQUEST": "true", "HTTP_HX_TRIGGER": "diagnostic-refresh"} if ajax else {}
    anonymous_response = request_client().get(reverse("core:computers"), **headers)
    regular_response = request_client(user=user_create()).get(reverse("core:computers"), **headers)

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

    with timezone.override("America/New_York"):
        response = client.get(reverse("core:computers"), {"issues-period": "30-days"})
        ajax_response = client.get(
            reverse("core:computers"),
            {"issues-period": "30-days", "issues-computer": computer_record.pk},
            HTTP_HX_REQUEST="true",
            HTTP_HX_TRIGGER="issue-filter",
        )

    content = response.content.decode()
    ajax_content = ajax_response.content.decode()
    failure = packet.events[-1]
    local_timestamp = datetime.fromtimestamp(failure.timestamp, ZoneInfo("America/New_York"))
    formatted_timestamp = date_format(local_timestamp, "Y-m-d H:i")

    assert response.status_code == 200
    assert "#icon-issues" not in content
    assert content.index("id=\"computer-list\"") < content.index("id=\"issues-content\"")
    assert "Close unsupported" in content
    assert computer_record.name in content
    assert "UID 1001" in content
    assert "failed &lt;script&gt;alert(1)&lt;/script&gt;" in content
    assert "failed <script>" not in content
    assert "sanea/js/diagnostic-logs.js" in content
    assert f"id=\"log-tab-{computer_record.pk}\"" in content
    logs_content = content.split("id=\"diagnostic-logs\"", 1)[1]
    assert "every 5s" not in logs_content
    assert "id=\"diagnostic-refresh\"" in logs_content
    assert "<use href=\"#icon-refresh\">" in logs_content
    assert "<use href=\"#icon-copy\">" in logs_content
    assert f"data-log-copy=\"{computer_record.pk}\"" in logs_content
    assert "title=\"Copy\" aria-label=\"Copy\"" in logs_content
    assert "<th scope=\"col\">Rule</th>" not in content
    assert "<th scope=\"col\">Window</th>" not in content
    assert f"<td class=\"small text-body-secondary\">{computer_record.name}</td>" in content
    assert "<td class=\"small text-body-secondary\">\n                                    <div>Close unsupported</div>" in content
    assert ajax_response.status_code == 200
    assert "id=\"issues-content\"" in ajax_content
    assert "sanea-shell" not in ajax_content
    assert f"<td class=\"small text-body-secondary text-nowrap\">{formatted_timestamp}</td>" in content
    assert f"<td class=\"small text-body-secondary text-nowrap\">{formatted_timestamp}</td>" in ajax_content


def test_diagnostic_refresh_returns_latest_snapshot_and_respects_filters(
    request_client: Callable[..., Client], user_create: Callable[..., User], computer_record: Computer,
) -> None:
    older = Computer.objects.create(
        hostname="older-computer", log_tail="older log", log_received=datetime(2026, 9, 28, tzinfo=UTC),
    )
    computer_record.replace_log_tail("original log", None)
    client = request_client(user=user_create(attributes={"is_staff": True}))
    headers = {"HTTP_HX_REQUEST": "true", "HTTP_HX_TRIGGER": "diagnostic-refresh"}

    initial = client.get(reverse("core:computers"), {"issues-period": "all", "log": older.pk}, **headers)
    computer_record.replace_log_tail("updated <script>alert(1)</script>", None)
    refreshed = client.get(reverse("core:computers"), {"issues-period": "7-days"}, **headers)
    selected = client.get(reverse("core:computers"), {"issues-period": "all", "issues-computer": older.pk}, **headers)
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

    response = client.get(reverse("core:computers"))
    fallback = client.get(reverse("core:computers"), {"issues-period": "all", "log": "missing"})
    content = response.content.decode()

    assert response.status_code == fallback.status_code == 200
    assert f"?issues-period=7-days&amp;log={computer_record.pk}#diagnostic-logs" in content
    assert f"id=\"diagnostic-computer\" name=\"log\" value=\"{computer_record.pk}\"" in fallback.content.decode()


@pytest.mark.parametrize("invalid", [False, True])
def test_diagnostic_refresh_handles_empty_logs_and_invalid_filters(
    request_client: Callable[..., Client], user_create: Callable[..., User], invalid: bool,
) -> None:
    client = request_client(user=user_create(attributes={"is_staff": True}))
    data = {"issues-period": "invalid" if invalid else "7-days"}

    response = client.get(
        reverse("core:computers"), data, HTTP_HX_REQUEST="true", HTTP_HX_TRIGGER="diagnostic-refresh",
    )
    content = response.content.decode()

    assert response.status_code == 200
    assert "Correct the filters" in content if invalid else "No diagnostic logs" in content
    assert "id=\"diagnostic-logs\"" in content
    assert "id=\"diagnostic-log-count\" hx-swap-oob=\"innerHTML\">0" in content


@pytest.mark.parametrize("ajax", [False, True])
def test_issue_filters_do_not_open_a_computer_dialog_or_change_overview_filters(
    request_client: Callable[..., Client], user_create: Callable[..., User], computer_record: Computer, ajax: bool,
) -> None:
    computer_record.replace_log_tail("synthetic selected log", None)
    headers = {"HTTP_HX_REQUEST": "true", "HTTP_HX_TRIGGER": "issue-filter"} if ajax else {}
    client = request_client(user=user_create(attributes={"is_staff": True}))

    response = client.get(
        reverse("core:computers"),
        {"issues-computer": computer_record.pk, "access": "blocked", "connection": "offline"},
        **headers,
    )
    content = response.content.decode()

    assert response.status_code == 200
    assert "synthetic selected log" in content
    assert "name=\"issues-computer\"" in content
    assert "name=\"issues-period\"" in content
    assert "id=\"computer-dialog-title\"" not in content
    assert "issues-period=7-days" in content
    assert "access=blocked" in content
    assert "connection=offline" in content


def test_live_computer_refresh_does_not_replace_logs(
    request_client: Callable[..., Client], user_create: Callable[..., User], computer_record: Computer,
) -> None:
    computer_record.replace_log_tail("synthetic stationary log", None)

    response = request_client(user=user_create(attributes={"is_staff": True})).get(
        reverse("core:computers"), HTTP_HX_REQUEST="true", HTTP_HX_TRIGGER="computer-live-refresh",
    )

    assert response.status_code == 200
    assert "id=\"diagnostic-logs\"" not in response.content.decode()
    assert "synthetic stationary log" not in response.content.decode()


@pytest.mark.parametrize("trigger", [None, "issue-filter", "diagnostic-refresh"])
def test_issue_calendar_bounds_failures_and_latest_log_snapshots_to_one_local_day(
    request_client: Callable[..., Client], user_create: Callable[..., User], computer_record: Computer, trigger: str | None,
) -> None:
    zone = ZoneInfo("America/New_York")
    since = int(datetime(2026, 10, 3, tzinfo=zone).timestamp())
    account = computer_record.accounts.get()
    packet = EventPacket.objects.create(account=account, sha256="a" * 64, first_seq=1, last_seq=3, event_count=3, byte_size=1)
    ActivityEvent.objects.bulk_create([
        ActivityEvent(account=account, packet=packet, seq=seq, type="enforcement_failed", timestamp=timestamp, reason=reason)
        for seq, timestamp, reason in ((1, since - 1, "before"), (2, since, "selected"), (3, since + 86_400, "after"))
    ])
    computer_record.log_tail = "synthetic-selected-log"
    computer_record.log_received = datetime.fromtimestamp(since, zone)
    computer_record.save(update_fields=("log_tail", "log_received"))
    Computer.objects.create(hostname="synthetic-before", log_tail="synthetic-before-log", log_received=datetime.fromtimestamp(since - 1, zone))
    Computer.objects.create(hostname="synthetic-after", log_tail="synthetic-after-log", log_received=datetime.fromtimestamp(since + 86_400, zone))
    client = request_client(user=user_create(attributes={"is_staff": True}))
    headers = {"HTTP_HX_REQUEST": "true", "HTTP_HX_TRIGGER": trigger} if trigger else {}

    with timezone.override(zone):
        response = client.get(reverse("core:computers"), {"issues-period": "day", "issues-day": "2026-10-03"}, **headers)

    content = response.content.decode()
    assert response.status_code == 200
    assert "synthetic-selected-log" in content
    assert "synthetic-before-log" not in content
    assert "synthetic-after-log" not in content
    assert "issues-day=2026-10-03" in content
    assert "Selected" in content if trigger != "diagnostic-refresh" else "id=\"issues-content\"" not in content
