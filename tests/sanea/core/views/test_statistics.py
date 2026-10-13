"""Tests for the dedicated activity statistics page."""

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
    local_start = datetime.fromtimestamp(packet.events[0].timestamp, ZoneInfo(computer_record.timezone))
    utc_last_used = datetime.fromtimestamp(packet.events[1].timestamp, UTC)
    received = account.event_packets.get().created

    assert response.status_code == 200
    assert "Statistics" in content
    assert "id=\"activity-filter\"" in content
    assert f"action=\"{reverse("core:statistics")}\"" in content
    assert f"hx-get=\"{reverse("core:statistics")}\"" in content
    assert "id=\"system-status\"" not in content
    assert "sanea-summary-card" not in content
    assert "vendor/chartjs/chart.umd.min.js" in content
    assert "sanea/js/activity-chart.js" in content
    assert "id=\"activity-chart\"" in content
    assert "50:17" in content
    assert "yandex_browser" in content
    assert "Launches" in content
    assert "Application usage" in content
    assert "3,137" not in content
    assert "Time totals include only completed sessions and application runs" in content
    assert "Other accounts in this selection may have older data." in content
    assert (
        f"Last activity data received for the selected accounts: {date_format(received, "SHORT_DATETIME_FORMAT")} (UTC)."
        in content
    )
    assert f"<div>{date_format(local_start, "SHORT_DATETIME_FORMAT")}</div>" in content
    assert "Asia/Novosibirsk" in content
    assert "Last used (UTC)" in content
    assert f"<td>{date_format(utc_last_used, "SHORT_DATETIME_FORMAT")}</td>" in content
    assert ajax_response.status_code == 200
    assert "id=\"activity-area\"" in ajax_content
    assert "yandex_browser" in ajax_content
    assert "sanea-shell" not in ajax_content


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
    assert "Last activity data received" not in pending_content
    assert "Screen time" not in pending_content

    packet = parse_event_packet(client_events_content, hashlib.sha256(client_events_content).hexdigest())
    account.store_event_packet(packet, len(client_events_content), None)

    received_response = client.get(reverse("core:statistics"))
    received_content = received_response.content.decode()

    assert "No activity events have been received" not in received_content
    assert "Last activity data received" in received_content
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
