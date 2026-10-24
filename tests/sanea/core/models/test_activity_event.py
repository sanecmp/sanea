"""Tests for activity report aggregation."""

import hashlib
import json
from collections.abc import Callable
from datetime import UTC, date, datetime
from typing import Any

import pytest
from django.utils import timezone
from sanelib.protocol import ApplicationIdentity, EmptyMeta, EventType, ProcessUpdateEvent, encode_event, parse_event_packet

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


@pytest.mark.parametrize("updates_first", [False, True])
def test_late_name_updates_relabel_active_and_completed_runs_without_rewriting_starts(
    domain_graph: dict[str, Any], updates_first: bool,
) -> None:
    account = domain_graph["account"]
    started = int(datetime(2026, 10, 1, 23, 59, tzinfo=UTC).timestamp())
    start = {
        "seq": 1, "type": "prc_start", "timestamp": started, "run_ident": 1,
        "prc_name": "tf_linux64", "exe": "/synthetic/tf_linux64",
        "application": {"ident": "steam:game:440", "name": "Steam game 440"},
        "meta": {"observed_via": "process"},
    }
    update = {
        "seq": 2, "type": "prc_update", "timestamp": started + 120, "run_ident": 1,
        "application": {"ident": "steam:game:440", "name": "Team Fortress 2"}, "meta": {},
    }
    records = (update, start) if updates_first else (start, update)

    for record in records:
        content = (json.dumps(record) + "\n").encode()
        packet = parse_event_packet(content, hashlib.sha256(content).hexdigest())
        account.store_event_packet(packet, len(content), None)
        assert not account.store_event_packet(packet, len(content), None)[1]

    accounts = Account.objects.filter(pk=account.pk)
    active = ActivityEvent.objects.build_report(accounts, date(2026, 10, 1), date(2026, 10, 2))
    assert active.applications[0].name == "Team Fortress 2"
    assert active.applications[0].launches == 1
    assert active.applications[0].duration is None
    assert active.applications[0].last_used == started
    assert active.recent == ()

    ending = {
        "seq": 3, "type": "prc_end", "timestamp": started + 180, "run_ident": 1,
        "duration": 150, "meta": {"actor": "user"},
    }
    content = (json.dumps(ending) + "\n").encode()
    account.store_event_packet(parse_event_packet(content, hashlib.sha256(content).hexdigest()), len(content), None)
    completed = ActivityEvent.objects.build_report(accounts, date(2026, 10, 1), date(2026, 10, 3))
    after_midnight = ActivityEvent.objects.build_report(accounts, date(2026, 10, 2), date(2026, 10, 3))

    assert completed.applications[0].name == completed.recent[0].app_name == "Team Fortress 2"
    assert completed.applications[0].duration == completed.recent[0].duration == 150
    assert completed.applications[0].launches == completed.recent[0].launches == 1
    assert after_midnight.applications == ()
    assert after_midnight.recent[0].app_name == "Team Fortress 2"
    assert account.activity_events.count() == 3
    stored_start = account.activity_events.get(seq=1)
    assert stored_start.app_name == "Steam game 440"
    assert (stored_start.prc_name, stored_start.exe) == ("tf_linux64", "/synthetic/tf_linux64")


@pytest.mark.parametrize(("target_index", "run_ident", "app_id", "expected_name"), [
    pytest.param(0, 1, "steam:game:440", "Team Fortress 2", id="same-run"),
    pytest.param(1, 1, "steam:game:440", "Steam game 440", id="other-account"),
    pytest.param(0, 0, "steam:game:440", "Steam game 440", id="other-run"),
    pytest.param(0, 1, "steam:game:570", "Steam game 440", id="other-app"),
])
def test_name_update_requires_the_same_account_run_and_application(
    activity_run_create: Callable[..., None], target_index: int, run_ident: int, app_id: str, expected_name: str,
) -> None:
    computer = Computer.objects.create(hostname="synthetic-name-updates", status="allowed")
    accounts = tuple(Account.objects.create(computer=computer, uid=uid, collect=True) for uid in (1001, 1002))
    started = int(datetime(2026, 10, 1, 12, tzinfo=UTC).timestamp())

    for account in accounts:
        activity_run_create(
            account, kind="prc", started=started, finished=None,
            application={"ident": "steam:game:440", "name": "Steam game 440"},
        )

    update = ProcessUpdateEvent(
        seq=2, type=EventType.PRC_UPDATE, timestamp=started + 10, run_ident=run_ident,
        application=ApplicationIdentity(ident=app_id, name="Team Fortress 2"), meta=EmptyMeta(),
    )
    content = encode_event(update)
    accounts[target_index].store_event_packet(
        parse_event_packet(content, hashlib.sha256(content).hexdigest()), len(content), None,
    )
    report = ActivityEvent.objects.build_report(Account.objects.filter(pk=accounts[0].pk), date(2026, 10, 1), date(2026, 10, 2))

    assert report.applications[0].name == expected_name
    assert report.applications[0].launches == 1


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
