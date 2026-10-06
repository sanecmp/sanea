"""Tests for activity report aggregation."""

import hashlib
from datetime import date
from typing import Any

import pytest
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
