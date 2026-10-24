"""Tests for activity report aggregation."""

import hashlib
import json
from collections.abc import Callable
from datetime import UTC, date, datetime
from typing import Any

import pytest
from django.utils import timezone
from sanelib.protocol import parse_event_packet

from sanea.core.models import Account, ActivityEvent, Computer


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


def test_report_groups_semantic_ids_not_shared_interpreters_or_helper_paths(
    domain_graph: dict[str, Any], activity_run_create: Callable[..., None],
) -> None:
    account = domain_graph["account"]
    started = int(datetime(2026, 10, 1, 12, tzinfo=UTC).timestamp())
    activity_run_create(account, kind="prc", started=started, finished=started + 60, duration=60,
                        prc_name="steamwebhelper", exe="/steam/steamwebhelper",
                        application={"ident": "steam:client", "name": "Steam"})
    activity_run_create(account, kind="prc", started=started + 60, finished=started + 120, duration=60,
                        prc_name="steam", exe="/steam/steam", application={"ident": "steam:client", "name": "Steam"})
    activity_run_create(account, kind="prc", started=started + 120, finished=started + 180, duration=60,
                        prc_name="gjs-console", exe="/usr/bin/gjs-console",
                        application={"ident": "gjs:/apps/maps.js", "name": "Maps"})
    activity_run_create(account, kind="prc", started=started + 180, finished=started + 240, duration=60,
                        prc_name="gjs-console", exe="/usr/bin/gjs-console",
                        application={"ident": "gjs:/apps/weather.js", "name": "Weather"})

    report = ActivityEvent.objects.build_report(Account.objects.filter(pk=account.pk), date(2026, 10, 1), date(2026, 10, 2))
    by_id = {usage.app_id: usage for usage in report.applications}

    assert report.summary.application_count == 3
    assert by_id["steam:client"].duration == 120
    assert by_id["steam:client"].launches == 2
    assert by_id["steam:client"].name == "Steam"
    assert {item.app_name for item in report.recent} == {"Steam", "Maps", "Weather"}
    assert account.activity_events.filter(prc_name="steamwebhelper", exe="/steam/steamwebhelper").count() == 1


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


@pytest.mark.parametrize("recent_limit", [0, 2])
def test_report_limits_recent_runs_per_kind_without_displacing_older_sessions(
    activity_run_create: Callable[..., None], recent_limit: int,
) -> None:
    computer = Computer.objects.create(hostname="synthetic-recent", status="allowed")
    account = Account.objects.create(computer=computer, uid=1001, collect=True)
    started = int(datetime(2026, 10, 1, 12, tzinfo=UTC).timestamp())

    for index in range(3):
        moment = started + index * 120
        activity_run_create(account, started=moment, finished=moment + 60, duration=60)
        activity_run_create(
            account, kind="prc", started=moment + 3_600, finished=moment + 3_660,
            duration=60, prc_name=f"synthetic-app-{index}",
        )

    report = ActivityEvent.objects.build_report(
        Account.objects.all(), date(2026, 10, 1), date(2026, 10, 2), recent_limit=recent_limit,
    )

    assert len(report.recent) == recent_limit * 2
    assert [item.kind for item in report.recent] == ["application"] * recent_limit + ["session"] * recent_limit
    assert all(item.started >= started + 120 for item in report.recent)


def test_recent_applications_group_all_runs_before_limiting_and_keep_distinct_ids(
    activity_run_create: Callable[..., None],
) -> None:
    computer = Computer.objects.create(hostname="synthetic-groups", status="allowed")
    account = Account.objects.create(computer=computer, uid=1001, collect=True)
    other_account = Account.objects.create(computer=computer, uid=1002, collect=True)
    started = int(datetime(2026, 10, 1, 12, tzinfo=UTC).timestamp())
    steam = {"ident": "steam:client", "name": "Steam"}
    activity_run_create(
        account, kind="prc", started=started, finished=started + 60, duration=60,
        application={"ident": "steam:game:440", "name": "Steam"},
    )

    for index in range(12):
        moment = started + (index + 1) * 120
        activity_run_create(
            account, kind="prc", started=moment, finished=moment + 60,
            duration=60, prc_name="steamwebhelper", application=steam,
        )

    activity_run_create(
        other_account, kind="prc", started=started + 3_600, finished=started + 3_720,
        duration=120, prc_name="steam", application=steam,
    )

    report = ActivityEvent.objects.build_report(
        Account.objects.all(), date(2026, 10, 1), date(2026, 10, 2), recent_limit=2,
    )

    assert len(report.recent) == 2
    client, game = report.recent
    assert client.app_id == "steam:client"
    assert client.launches == 13
    assert client.duration == 840
    assert client.account_ids == (account.pk, other_account.pk)
    assert client.started == started + 3_600
    assert game.app_id == "steam:game:440"
    assert game.launches == 1


def test_recent_sessions_use_completion_date_even_when_they_started_before_the_period(
    activity_run_create: Callable[..., None],
) -> None:
    computer = Computer.objects.create(hostname="synthetic-overnight", status="allowed")
    account = Account.objects.create(computer=computer, uid=1001, collect=True)
    midnight = int(datetime(2026, 10, 2, 4, tzinfo=UTC).timestamp())
    activity_run_create(account, started=midnight - 3_600, finished=midnight, duration=600)
    activity_run_create(account, started=midnight - 7_200, finished=midnight + 60, duration=300)
    activity_run_create(account, started=midnight, finished=midnight + 86_400, duration=120)
    activity_run_create(account, started=midnight + 60, finished=None)

    with timezone.override("America/New_York"):
        report = ActivityEvent.objects.build_report(Account.objects.all(), date(2026, 10, 2), date(2026, 10, 3))

    assert [item.duration for item in report.recent] == [300, 600]
    assert all(item.kind == "session" for item in report.recent)
    assert report.recent[0].started < midnight
