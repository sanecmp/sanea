"""Tests for activity report aggregation."""

import hashlib
import json
from datetime import UTC, date, datetime
from typing import Any

import pytest
from django.utils import timezone
from sanelib.protocol import parse_event_packet

from sanea.core.models import ActivityEvent


def test_report_aggregates_completed_sessions_and_applications(
    domain_graph: dict[str, Any],
    activity_events_content: bytes,
) -> None:
    account = domain_graph["account"]
    digest = hashlib.sha256(activity_events_content).hexdigest()
    packet = parse_event_packet(activity_events_content, digest)
    account.store_event_packet(packet, len(activity_events_content), None)

    report = ActivityEvent.objects.build_report(
        type(account).objects.filter(pk=account.pk),
        date(2026, 10, 1),
        date(2026, 10, 2),
    )

    assert report.summary.screen_time == 3017
    assert report.summary.session_count == 1
    assert report.summary.application_count == 1
    assert report.daily_screen_time[0].day == date(2026, 10, 1)
    assert report.daily_screen_time[0].person_id == domain_graph["person"].pk
    assert report.daily_screen_time[0].duration == 3017
    assert report.applications[0].prc_name == "yandex_browser"
    assert report.applications[0].exe == "/opt/yandex/browser/yandex_browser"
    assert report.applications[0].launches == 1
    assert report.applications[0].duration == 3137
    assert [row.kind for row in report.recent] == ["application", "session"]


def test_report_rejects_invalid_bounds(domain_graph: dict[str, Any]) -> None:
    accounts = type(domain_graph["account"]).objects.all()

    with pytest.raises(ValueError, match="till must be later than since"):
        ActivityEvent.objects.build_report(
            accounts,
            date(2026, 10, 2),
            date(2026, 10, 2),
        )


@pytest.mark.parametrize("duration", [0, 3137])
def test_report_distinguishes_pending_duration_from_completed_zero(
    domain_graph: dict[str, Any],
    activity_events_content: bytes,
    duration: int,
) -> None:
    account = domain_graph["account"]
    lines = activity_events_content.splitlines(keepends=True)
    starts_content = b"".join(lines[:2])
    starts_packet = parse_event_packet(starts_content, hashlib.sha256(starts_content).hexdigest())
    account.store_event_packet(starts_packet, len(starts_content), None)
    accounts = type(account).objects.filter(pk=account.pk)
    since, till = date(2026, 10, 1), date(2026, 10, 2)

    pending_report = ActivityEvent.objects.build_report(accounts, since, till)

    assert pending_report.applications[0].duration is None
    assert pending_report.applications[0].launches == 1
    assert pending_report.summary.application_count == 1
    assert pending_report.recent == ()
    assert ActivityEvent.objects.count() == 2

    ending = json.loads(lines[3])
    ending["duration"] = duration
    ending_content = (json.dumps(ending) + "\n").encode()
    ending_packet = parse_event_packet(ending_content, hashlib.sha256(ending_content).hexdigest())
    account.store_event_packet(ending_packet, len(ending_content), None)

    completed_report = ActivityEvent.objects.build_report(accounts, since, till)

    assert completed_report.applications[0].duration == duration
    assert completed_report.applications[0].launches == 1
    assert completed_report.recent[0].duration == duration
    assert ActivityEvent.objects.count() == 3


def test_report_keeps_completed_duration_when_another_launch_is_pending(
    domain_graph: dict[str, Any],
    activity_events_content: bytes,
) -> None:
    account = domain_graph["account"]
    packet = parse_event_packet(activity_events_content, hashlib.sha256(activity_events_content).hexdigest())
    account.store_event_packet(packet, len(activity_events_content), None)
    launch = json.loads(activity_events_content.splitlines()[1])
    launch.update(seq=142, run_ident=142, timestamp=1_790_845_600)
    launch_content = (json.dumps(launch) + "\n").encode()
    launch_packet = parse_event_packet(launch_content, hashlib.sha256(launch_content).hexdigest())
    account.store_event_packet(launch_packet, len(launch_content), None)

    report = ActivityEvent.objects.build_report(
        type(account).objects.filter(pk=account.pk), date(2026, 10, 1), date(2026, 10, 2),
    )

    assert len(report.applications) == 1
    assert report.applications[0].duration == 3137
    assert report.applications[0].launches == 2
    assert len(report.recent) == 2


def test_report_uses_sanea_timezone_for_period_bounds_and_daily_totals(
    domain_graph: dict[str, Any],
    activity_events_content: bytes,
) -> None:
    account = domain_graph["account"]
    events = [json.loads(line) for line in activity_events_content.splitlines()]
    timestamp = int(datetime(2026, 10, 2, 2, tzinfo=UTC).timestamp())
    offset = timestamp - events[0]["timestamp"]

    for event in events:
        event["timestamp"] += offset

    content = ("\n".join(json.dumps(event) for event in events) + "\n").encode()
    packet = parse_event_packet(content, hashlib.sha256(content).hexdigest())
    account.store_event_packet(packet, len(content), None)
    accounts = type(account).objects.filter(pk=account.pk)

    with timezone.override("America/New_York"):
        local_report = ActivityEvent.objects.build_report(accounts, date(2026, 10, 1), date(2026, 10, 2))
        next_day_report = ActivityEvent.objects.build_report(accounts, date(2026, 10, 2), date(2026, 10, 3))

    assert domain_graph["computer"].timezone == "Asia/Novosibirsk"
    assert local_report.summary.screen_time == 3017
    assert local_report.daily_screen_time[0].day == date(2026, 10, 1)
    assert local_report.applications[0].duration == 3137
    assert next_day_report.summary.screen_time == 0
    assert next_day_report.daily_screen_time == ()
    assert next_day_report.applications == ()
