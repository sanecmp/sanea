"""Tests for the dedicated activity statistics page."""

import hashlib
import json
from collections.abc import Callable
from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

import pytest
from django.test import Client
from django.urls import reverse
from django.utils import timezone
from django.utils.formats import date_format
from sanelib.protocol import parse_event_packet
from time_machine import TimeMachineFixture

from sanea.core.models import Computer, User


@pytest.mark.parametrize(
    "request_options",
    [{}, {"HTTP_HX_REQUEST": "true", "HTTP_HX_TRIGGER": "activity-filter"}],
    ids=["page", "fragment"],
)
def test_statistics_requires_authenticated_management_user(
    request_client: Callable[..., Client],
    user_create: Callable[..., User],
    request_options: dict[str, str],
) -> None:
    regular_user = user_create()

    anonymous = request_client().get(reverse("core:statistics"), **request_options)
    regular = request_client(user=regular_user).get(reverse("core:statistics"), **request_options)

    assert anonymous.status_code == 302
    assert anonymous.url.startswith(reverse("core:sign_in"))
    assert regular.status_code == 403


def test_statistics_filters_and_renders_received_activity(
    request_client: Callable[..., Client],
    user_create: Callable[..., User],
    computer_record: Computer,
    client_events_content: bytes,
    calendar_time: TimeMachineFixture,
) -> None:
    staff_user = user_create(attributes={"is_staff": True})
    account = computer_record.accounts.get()
    digest = hashlib.sha256(client_events_content).hexdigest()
    packet = parse_event_packet(client_events_content, digest)
    account.store_event_packet(packet, len(client_events_content), None)
    other_account = computer_record.accounts.create(uid=1002, login="other", name="Other", collect=True)
    calendar_time.move_to("2026-10-06T13:00:00+00:00", tick=False)
    other_account.store_event_packet(packet, len(client_events_content), None)
    client = request_client(user=staff_user)
    filters = {"period": "7-days", "computer": computer_record.pk, "account": account.pk}

    with timezone.override("America/New_York"):
        response = client.get(reverse("core:statistics"), filters)
        ajax_response = client.get(
            reverse("core:statistics"), filters,
            HTTP_HX_REQUEST="true", HTTP_HX_TRIGGER="activity-filter",
        )

    content = response.content.decode()
    ajax_content = ajax_response.content.decode()
    zone = ZoneInfo("America/New_York")
    local_start = datetime.fromtimestamp(packet.events[0].timestamp, zone)
    local_last_used = datetime.fromtimestamp(packet.events[1].timestamp, zone)
    received = timezone.localtime(account.event_packets.get().created, zone)

    assert response.status_code == 200
    assert "Statistics" in content
    assert "id=\"activity-filter\"" in content
    assert f"action=\"{reverse("core:statistics")}\"" in content
    assert f"hx-get=\"{reverse("core:statistics")}\"" in content
    assert "id=\"system-status\"" not in content
    assert "sanea-summary-card" not in content
    assert "vendor/chartjs/chart.umd.min.js" in content
    assert "sanea/js/activity-charts.js" in content
    assert "sanea/js/statistics.js" in content
    assert "sanea/css/tables.css" in content
    assert "sanea/css/statistics.css" in content
    assert "id=\"activity-chart\"" in content
    assert "50:17" in content
    assert "yandex_browser" in content
    assert "Launches" in content
    assert "Application usage" in content
    assert "col-xl-7" not in content
    assert "col-xl-5" not in content
    assert "3,137" not in content
    assert "Time totals include only completed sessions and application runs" not in content
    assert "Other accounts in this selection may have older data." not in content
    assert "class=\"table-responsive sanea-table-wrap\"" in content
    assert ajax_response.status_code == 200
    assert "id=\"activity-area\"" in ajax_content
    assert "yandex_browser" in ajax_content
    assert "sanea-shell" not in ajax_content

    for rendered in (content, ajax_content):
        assert (
            f"Last received: {date_format(received, "SHORT_DATETIME_FORMAT")}"
            in rendered
        )
        assert f"<div>{date_format(local_start, "Y-m-d H:i")}</div>" in rendered
        assert "America/New_York" in rendered
        assert "Asia/Novosibirsk" not in rendered
        assert "(UTC)" not in rendered
        assert "Last used" in rendered
        assert (
            "<td class=\"small text-body-secondary text-end text-nowrap\">"
            f"{date_format(local_last_used, "Y-m-d H:i")}</td>"
        ) in rendered


@pytest.mark.parametrize(
    "request_options",
    [{}, {"HTTP_HX_REQUEST": "true", "HTTP_HX_TRIGGER": "activity-filter"}],
    ids=["page", "fragment"],
)
@pytest.mark.parametrize(
    ("language", "explanation"),
    [
        ("en", "No duration yet"),
        ("ru", "Длительности пока нет"),
    ],
)
def test_statistics_shows_a_dash_until_application_end_is_received(
    request_client: Callable[..., Client],
    user_create: Callable[..., User],
    computer_record: Computer,
    client_events_content: bytes,
    request_options: dict[str, str],
    language: str,
    explanation: str,
) -> None:
    account = computer_record.accounts.get()
    lines = client_events_content.splitlines(keepends=True)
    content = b"".join(lines[:2])
    packet = parse_event_packet(content, hashlib.sha256(content).hexdigest())
    account.store_event_packet(packet, len(content), None)
    client = request_client(user=user_create(attributes={"is_staff": True}))

    response = client.get(
        reverse("core:statistics"), {"period": "7-days"}, HTTP_ACCEPT_LANGUAGE=language, **request_options,
    )
    rendered = response.content.decode()

    assert response.status_code == 200
    assert "yandex_browser" in rendered
    assert f"title=\"{explanation}\">—</td>" in rendered
    assert ">0:00</td>" not in rendered

    ending_content = lines[3]
    ending_packet = parse_event_packet(ending_content, hashlib.sha256(ending_content).hexdigest())
    account.store_event_packet(ending_packet, len(ending_content), None)

    completed_response = client.get(
        reverse("core:statistics"), {"period": "7-days"}, HTTP_ACCEPT_LANGUAGE=language, **request_options,
    )
    completed = completed_response.content.decode()

    assert completed_response.status_code == 200
    assert ">52:17</td>" in completed
    assert ">—</td>" not in completed


def test_statistics_today_chart_uses_the_sanea_day_instead_of_the_computer_day(
    request_client: Callable[..., Client],
    user_create: Callable[..., User],
    computer_record: Computer,
    client_events_content: bytes,
    calendar_time: TimeMachineFixture,
) -> None:
    events = [json.loads(line) for line in client_events_content.splitlines()]
    timestamp = int(datetime(2026, 10, 2, 2, tzinfo=UTC).timestamp())
    offset = timestamp - events[0]["timestamp"]

    for event in events:
        event["timestamp"] += offset

    content = ("\n".join(json.dumps(event) for event in events) + "\n").encode()
    packet = parse_event_packet(content, hashlib.sha256(content).hexdigest())
    computer_record.accounts.get().store_event_packet(packet, len(content), None)
    calendar_time.move_to("2026-10-02T03:30:00+00:00", tick=False)
    client = request_client(user=user_create(attributes={"is_staff": True}))

    with timezone.override("America/New_York"):
        response = client.get(reverse("core:statistics"))

    rendered = response.content.decode()
    chart_content = rendered.split('<script id="activity-chart-data" type="application/json">', 1)[1].split("</script>", 1)[0]
    chart = json.loads(chart_content)

    assert response.status_code == 200
    assert computer_record.timezone == "Asia/Novosibirsk"
    assert chart["labels"] == [date_format(date(2026, 10, 1), "SHORT_DATE_FORMAT")]
    assert chart["datasets"][0]["data"] == [3017]
    assert "yandex_browser" in rendered


def test_statistics_explains_missing_activity_collection(
    request_client: Callable[..., Client],
    user_create: Callable[..., User],
) -> None:
    staff_user = user_create(attributes={"is_staff": True})

    response = request_client(user=staff_user).get(reverse("core:statistics"))
    content = response.content.decode()

    assert response.status_code == 200
    assert "No accounts with activity collection enabled match this selection." in content
    assert f"href=\"{reverse("core:accounts")}\"" in content
    assert "Screen time" not in content
    assert "No activity events have been received" not in content
    assert "Correct the filters to view activity." not in content
    assert "id=\"system-status\"" not in content


def test_statistics_distinguishes_missing_events_from_no_activity_in_the_period(
    request_client: Callable[..., Client],
    user_create: Callable[..., User],
    computer_record: Computer,
    client_events_content: bytes,
) -> None:
    staff_user = user_create(attributes={"is_staff": True})
    client = request_client(user=staff_user)
    account = computer_record.accounts.get()

    pending_response = client.get(reverse("core:statistics"))
    pending_content = pending_response.content.decode()

    assert "No activity events have been received for these accounts yet." in pending_content
    assert "Last received:" not in pending_content
    assert "Screen time" not in pending_content

    packet = parse_event_packet(client_events_content, hashlib.sha256(client_events_content).hexdigest())
    account.store_event_packet(packet, len(client_events_content), None)

    received_response = client.get(reverse("core:statistics"))
    received_content = received_response.content.decode()

    assert "No activity events have been received" not in received_content
    assert "Last received:" in received_content
    assert "No screen time was recorded for this period." in received_content
    assert "No application use was recorded for this period." in received_content


@pytest.mark.parametrize(
    "request_options",
    [{}, {"HTTP_HX_REQUEST": "true", "HTTP_HX_TRIGGER": "activity-filter"}],
    ids=["page", "fragment"],
)
def test_statistics_rejects_invalid_filters(
    request_client: Callable[..., Client],
    user_create: Callable[..., User],
    request_options: dict[str, str],
) -> None:
    staff_user = user_create(attributes={"is_staff": True})

    response = request_client(user=staff_user).get(
        reverse("core:statistics"), {"period": "invalid"}, **request_options,
    )
    content = response.content.decode()

    assert response.status_code == 200
    assert "Correct the filters to view activity." in content
    assert "id=\"activity-chart\"" not in content


@pytest.mark.parametrize(
    "request_options",
    [{}, {"HTTP_HX_REQUEST": "true", "HTTP_HX_TRIGGER": "activity-filter"}],
    ids=["page", "filter"],
)
@pytest.mark.parametrize("kind", ["application", "session", "invalid"])
def test_statistics_separates_recent_kinds_and_retains_the_tab_with_filters(
    request_client: Callable[..., Client],
    user_create: Callable[..., User],
    computer_record: Computer,
    activity_run_create: Callable[..., None],
    request_options: dict[str, str],
    kind: str,
) -> None:
    account = computer_record.accounts.get()
    started = int(timezone.now().timestamp()) - 7_200
    activity_run_create(account, started=started, finished=started + 60, duration=60)

    for index in range(12):
        moment = started + (index + 1) * 120
        activity_run_create(
            account, kind="prc", started=moment, finished=moment + 60,
            duration=60, prc_name=f"synthetic-app-{index}",
        )

    client = request_client(user=user_create(attributes={"is_staff": True}))
    selected_kind = kind if kind != "invalid" else "application"

    response = client.get(
        reverse("core:statistics"), {"period": "7-days", "account": account.pk, "activity_kind": kind},
        **request_options,
    )
    content = response.content.decode()
    applications = content.split("id=\"recent-application-panel\"", 1)[1].split("id=\"recent-session-panel\"", 1)[0]
    sessions = content.split("id=\"recent-session-panel\"", 1)[1].split("<section class=\"card\">", 1)[0]

    assert response.status_code == 200
    assert applications.count("role=\"listitem\"") == 10
    assert sessions.count("role=\"listitem\"") == 1
    assert "synthetic-app-11" in applications
    assert "synthetic-app-0<" not in applications
    assert "synthetic-app-" not in sessions
    assert account.name in sessions
    assert f"id=\"recent-activity-kind\" name=\"activity_kind\" value=\"{selected_kind}\"" in content
    assert f"class=\"nav-link active\" id=\"recent-{selected_kind}-tab\"" in content
    assert f"?period=7-days&amp;account={account.pk}&amp;activity_kind=session" in content
    assert f"?period=7-days&amp;account={account.pk}&amp;activity_kind=application" in content


@pytest.mark.parametrize(
    ("kind", "missing_kind", "empty_message"),
    [
        ("session", "application", "No completed application runs for this period."),
        ("prc", "session", "No completed sessions for this period."),
    ],
)
def test_statistics_has_a_separate_empty_state_for_each_recent_kind(
    request_client: Callable[..., Client],
    user_create: Callable[..., User],
    computer_record: Computer,
    activity_run_create: Callable[..., None],
    kind: str,
    missing_kind: str,
    empty_message: str,
) -> None:
    started = int(timezone.now().timestamp()) - 3_600
    account = computer_record.accounts.get()
    activity_run_create(account, kind=kind, started=started, finished=started + 600, duration=600)
    client = request_client(user=user_create(attributes={"is_staff": True}))

    response = client.get(reverse("core:statistics"), {"activity_kind": missing_kind, "period": "today"})
    content = response.content.decode()

    assert response.status_code == 200
    assert empty_message in content
    assert f"class=\"nav-link active\" id=\"recent-{missing_kind}-tab\"" in content


@pytest.mark.parametrize("fragment", [False, True], ids=["page", "fragment"])
def test_statistics_calendar_filters_one_local_day_and_groups_recent_applications(
    request_client: Callable[..., Client], user_create: Callable[..., User], computer_record: Computer,
    activity_run_create: Callable[..., None], fragment: bool,
) -> None:
    account = computer_record.accounts.get()
    started = int(datetime(2026, 10, 2, 2, tzinfo=UTC).timestamp())
    activity_run_create(
        account, kind="prc", started=started, finished=started + 60, duration=60,
        application={"ident": "steam:game:440", "name": "Team Fortress 2"},
    )
    activity_run_create(
        account, kind="prc", started=started + 120, finished=started + 180, duration=60,
        application={"ident": "steam:game:440", "name": "Team Fortress 2"},
    )
    client = request_client(user=user_create(attributes={"is_staff": True}))
    request_options = {"HTTP_HX_REQUEST": "true", "HTTP_HX_TRIGGER": "activity-filter"} if fragment else {}

    with timezone.override("America/New_York"):
        response = client.get(
            reverse("core:statistics"), {"period": "day", "day": "2026-10-01", "activity_kind": "session"},
            **request_options,
        )

    content = response.content.decode()
    recent = content.split("id=\"recent-application-panel\"", 1)[1].split("id=\"recent-session-panel\"", 1)[0]
    assert response.status_code == 200
    assert recent.count("role=\"listitem\"") == 1
    assert "Team Fortress 2" in recent
    assert "Launches: 2" in recent
    assert "<div>2:00</div>" in recent
    assert "value=\"2026-10-01\"" in content
    assert "period=day&amp;day=2026-10-01&amp;activity_kind=application" in content

    if not fragment:
        assert "vendor/flatpickr/flatpickr.min.js" in content
        assert "vendor/flatpickr/flatpickr.min.css" in content
        assert "vendor/flatpickr/ru.js" in content
