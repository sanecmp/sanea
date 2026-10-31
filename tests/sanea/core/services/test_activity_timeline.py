"""Tests for rolling-window usage aggregation."""

import hashlib
import json
from collections.abc import Callable
from datetime import UTC, date, datetime

import pytest
from sanelib.protocol import parse_event_packet

from sanea.core.models import Account, ActivityEvent, Computer, Person
from sanea.core.services.activity_timeline import build_usage_timeline


def test_timeline_uses_identity_even_when_display_name_or_helper_executable_changes(
    activity_run_create: Callable[..., None],
) -> None:
    computer = Computer.objects.create(hostname="synthetic-identities", status="allowed")
    account = Account.objects.create(computer=computer, uid=1001, collect=True)
    activity_run_create(account, kind="prc", started=100, finished=160, duration=60, exe="/old/helper",
                        application={"ident": "desktop:org.example.Editor", "name": "Editor"})
    activity_run_create(account, kind="prc", started=160, finished=220, duration=60, exe="/new/helper",
                        application={"ident": "desktop:org.example.Editor", "name": "Renamed editor"})

    timeline = build_usage_timeline(Account.objects.all(), 100, 220)

    assert timeline.applications == {("Renamed editor", "desktop:org.example.Editor"): 120}


def test_timeline_combines_accounts_and_clips_completed_runs_to_the_window(activity_run_create: Callable[..., None]) -> None:
    since = 1_790_000_000
    till = since + 48 * 3_600
    person = Person.objects.create(name="Synthetic person")
    computer = Computer.objects.create(hostname="synthetic-desktop", status="allowed")
    laptop = Computer.objects.create(hostname="synthetic-laptop", status="allowed")
    first = Account.objects.create(computer=computer, person=person, uid=1001, collect=True)
    second = Account.objects.create(computer=laptop, person=person, uid=1001, collect=True)
    guest = Account.objects.create(computer=computer, uid=1002, collect=True)
    excluded = Account.objects.create(computer=computer, person=person, uid=1003, collect=True)
    activity_run_create(
        first, started=since - 3_600, finished=since + 3_600, duration=3_600,
        intervals=[{"timestamp": since + 1_800, "duration": 3_600}],
    )
    activity_run_create(second, started=since + 1_800, finished=since + 5_400, duration=3_600)
    activity_run_create(guest, started=since + 3_600, finished=since + 7_200, duration=1_800)
    activity_run_create(excluded, started=since, finished=since + 7_200, duration=7_200)
    excluded.collect = False
    excluded.save(update_fields=("collect",))
    activity_run_create(
        first, kind="prc", started=since - 3_600, finished=since + 3_600, duration=3_600,
        intervals=[{"timestamp": since + 1_800, "duration": 3_600}],
    )
    activity_run_create(second, kind="prc", started=since + 3_600, finished=since + 7_200, duration=1_800)
    activity_run_create(
        guest, kind="prc", started=since + 3_600, finished=since + 7_200,
        duration=600, exe="/other/synthetic-app",
    )

    timeline = build_usage_timeline(Account.objects.filter(collect=True), since, till)

    assert timeline.buckets == tuple(range(since, till, 3_600))
    assert timeline.people[person.pk] == (3_600, 1_800) + (0,) * 46
    assert timeline.people[None] == (0, 1_800) + (0,) * 46
    assert timeline.applications == {
        ("synthetic-app", "/demo/synthetic-app"): 3_600,
        ("synthetic-app", "/other/synthetic-app"): 600,
    }


@pytest.mark.parametrize("kind", ["session", "prc"])
@pytest.mark.parametrize(
    ("started", "finished", "duration", "expected"),
    [
        pytest.param(-3_600, 0, 3_600, 0, id="ends-at-lower-bound"),
        pytest.param(0, 3_600, 3_600, 3_600, id="starts-at-lower-bound"),
        pytest.param(0, 7_200, 3_600, 3_600, id="ends-at-upper-bound"),
        pytest.param(0, 7_201, 3_600, 3_599, id="received-after-upper-bound"),
        pytest.param(7_200, 7_201, 1, 0, id="starts-at-upper-bound"),
        pytest.param(0, None, 0, 0, id="ongoing"),
        pytest.param(3_600, 3_600, 100, 100, id="same-start-and-end-timestamp"),
        pytest.param(3_600, 1_800, 100, 100, id="clock-went-backwards"),
        pytest.param(0, 3_600, 0, 0, id="zero-active-time"),
    ],
)
def test_timeline_uses_known_intervals_instead_of_run_start_and_end_bounds(
    activity_run_create: Callable[..., None],
    kind: str,
    started: int,
    finished: int | None,
    duration: int,
    expected: int,
) -> None:
    since = 1_790_000_000
    computer = Computer.objects.create(hostname="synthetic-desktop", status="allowed")
    account = Account.objects.create(computer=computer, uid=1001, collect=True)
    activity_run_create(
        account, kind=kind, started=since + started,
        finished=None if finished is None else since + finished, duration=duration,
    )

    timeline = build_usage_timeline(Account.objects.all(), since, since + 7_200)

    assert sum(sum(hourly) for hourly in timeline.people.values()) + sum(timeline.applications.values()) == expected


def test_timeline_returns_explicit_hours_without_activity() -> None:
    timeline = build_usage_timeline(Account.objects.none(), 1_790_000_000, 1_790_007_300)

    assert len(timeline.buckets) == 3
    assert timeline.people == {}
    assert timeline.applications == {}


def test_timeline_aligns_buckets_without_extending_the_usage_window(activity_run_create: Callable[..., None]) -> None:
    since = 1_790_000_000
    till = since + 7_200
    computer = Computer.objects.create(hostname="synthetic-aligned-hours", status="allowed")
    account = Account.objects.create(computer=computer, uid=1001, collect=True)

    for kind in ("session", "prc"):
        activity_run_create(
            account, kind=kind, started=since - 3_600, finished=till, duration=5_400,
            intervals=[{"timestamp": since + 3_600, "duration": 5_400}],
        )
        activity_run_create(account, kind=kind, started=since - 1_200, finished=since - 1, duration=1_199)
        activity_run_create(account, kind=kind, started=till - 600, finished=till + 1, duration=601)

    timeline = build_usage_timeline(
        Account.objects.all(), since, till, bucket_boundaries=(since - 1_500, since + 2_100, since + 5_700, till),
    )

    assert timeline.buckets == (since - 1_500, since + 2_100, since + 5_700)
    assert timeline.people == {None: (2_100, 1_500, 600)}
    assert sum(timeline.people[None]) == 4_200
    assert timeline.applications == {("synthetic-app", "/demo/synthetic-app"): 4_200}


@pytest.mark.parametrize(
    "boundaries",
    [
        (), (10_000,), (10_001, 20_000), (6_400, 10_000, 20_000),
        (10_000, 15_000, 14_000, 20_000), (10_000, 15_000, 15_000, 20_000), (10_000, 19_999), (10_000, 20_001),
    ],
)
def test_timeline_rejects_invalid_explicit_boundaries(boundaries: tuple[int, ...]) -> None:

    with pytest.raises(ValueError, match="bucket boundaries must increase, contain since in the first interval and end at till"):
        build_usage_timeline(Account.objects.none(), 10_000, 20_000, bucket_boundaries=boundaries)


def test_timeline_splits_at_explicit_boundaries_without_rescaling_time(activity_run_create: Callable[..., None]) -> None:
    computer = Computer.objects.create(hostname="synthetic-calendar-days", status="allowed")
    account = Account.objects.create(computer=computer, uid=1001, collect=True)
    activity_run_create(account, started=10_000, finished=25_000, duration=15_000)

    timeline = build_usage_timeline(
        Account.objects.all(), 10_000, 25_000, bucket_boundaries=(10_000, 13_600, 20_800, 25_000),
    )

    assert timeline.buckets == (10_000, 13_600, 20_800)
    assert timeline.people == {None: (3_600, 7_200, 4_200)}


@pytest.mark.parametrize(("since", "till"), [(100, 100), (101, 100), (-1, 100)])
def test_timeline_rejects_invalid_bounds(since: int, till: int) -> None:

    with pytest.raises(ValueError, match="require 0 <= since < till"):
        build_usage_timeline(Account.objects.none(), since, till)


def test_timeline_can_group_longer_periods_without_losing_partial_intervals(activity_run_create: Callable[..., None]) -> None:
    since = 1_790_000_000
    computer = Computer.objects.create(hostname="synthetic-desktop", status="allowed")
    account = Account.objects.create(computer=computer, uid=1001, collect=True)
    activity_run_create(
        account, started=since + 43_200, finished=since + 129_600, duration=7_200,
        intervals=[
            {"timestamp": since + 86_400, "duration": 3_600},
            {"timestamp": since + 129_600, "duration": 3_600},
        ],
    )

    timeline = build_usage_timeline(Account.objects.all(), since, since + 129_600, bucket_seconds=86_400)

    assert timeline.buckets == (since, since + 86_400)
    assert timeline.people[None] == (3_600, 3_600)


@pytest.mark.parametrize(
    ("kind", "expected_people", "expected_applications"),
    [
        ("session", {None: (1_200,) + (0,) * 23 + (1_200,) + (0,) * 23}, {}),
        ("prc", {}, {("synthetic-app", "/demo/synthetic-app"): 2_400}),
    ],
)
@pytest.mark.parametrize("end_offset", [-3_600, 172_800])
def test_timeline_keeps_sleep_empty_and_uses_intervals_even_when_the_end_timestamp_is_outside_the_window(
    activity_run_create: Callable[..., None], kind: str, end_offset: int,
    expected_people: dict[int | None, tuple[int, ...]], expected_applications: dict[tuple[str, str], int],
) -> None:
    since = 1_790_000_000
    computer = Computer.objects.create(hostname="synthetic-sleep-intervals", status="allowed")
    account = Account.objects.create(computer=computer, uid=1001, collect=True)
    activity_run_create(
        account, kind=kind, started=since - 86_400, finished=since + end_offset, duration=2_400,
        intervals=[
            {"timestamp": since + 3_600, "duration": 1_200},
            {"timestamp": since + 90_000, "duration": 1_200},
        ],
    )

    timeline = build_usage_timeline(Account.objects.all(), since, since + 48 * 3_600)

    assert timeline.people == expected_people
    assert timeline.applications == expected_applications


@pytest.mark.parametrize("kind", ["session", "prc"])
def test_timeline_does_not_invent_intervals_for_an_unknown_history(
    activity_run_create: Callable[..., None], kind: str,
) -> None:
    computer = Computer.objects.create(hostname="synthetic-unknown-history", status="allowed")
    account = Account.objects.create(computer=computer, uid=1001, collect=True)
    activity_run_create(account, kind=kind, started=10_000, finished=20_000, duration=3_600, intervals=None)

    timeline = build_usage_timeline(Account.objects.all(), 10_000, 20_000)

    assert timeline.people == {}
    assert timeline.applications == {}
    assert account.activity_events.get(type=f"{kind}_end").duration == 3_600


@pytest.mark.parametrize("kind", ["session", "prc"])
def test_timeline_uses_the_most_complete_end_once_when_a_stale_state_replays_the_same_run(
    activity_run_create: Callable[..., None], kind: str,
) -> None:
    computer = Computer.objects.create(hostname="synthetic-replayed-ending", status="allowed")
    account = Account.objects.create(computer=computer, uid=1001, collect=True)
    activity_run_create(account, kind=kind, started=10_000, finished=14_000, duration=2_400)
    original_end = account.activity_events.get(type=f"{kind}_end")
    replayed_end = {
        "seq": original_end.seq + 1,
        "type": original_end.type,
        "run_ident": original_end.run_ident,
        "timestamp": 15_000,
        "duration": 1_200,
        "intervals": [{"timestamp": 15_000, "duration": 1_200}],
        "meta": {"actor": "user"},
    }
    content = (json.dumps(replayed_end) + "\n").encode()
    account.store_event_packet(parse_event_packet(content, hashlib.sha256(content).hexdigest()), len(content), None)

    timeline = build_usage_timeline(Account.objects.all(), 10_000, 17_200)

    assert sum(sum(durations) for durations in timeline.people.values()) + sum(timeline.applications.values()) == 2_400
    assert account.activity_events.filter(type=f"{kind}_end").count() == 2


@pytest.mark.parametrize("bucket_seconds", [0, -1])
def test_timeline_rejects_nonpositive_chart_intervals(bucket_seconds: int) -> None:

    with pytest.raises(ValueError, match="bucket_seconds must be positive"):
        build_usage_timeline(Account.objects.none(), 100, 200, bucket_seconds=bucket_seconds)


def test_reports_omit_desktop_components_without_deleting_events_or_affecting_screen_time(
    activity_run_create: Callable[..., None],
) -> None:
    computer = Computer.objects.create(hostname="synthetic-desktop-components", status="allowed")
    account = Account.objects.create(computer=computer, uid=1001, collect=True)
    started = int(datetime(2026, 10, 1, 12, tzinfo=UTC).timestamp())
    activity_run_create(account, started=started, finished=started + 3_600, duration=3_600)
    activity_run_create(
        account, kind="prc", started=started, finished=started + 3_600,
        duration=3_600, prc_name="mutter-x11-fram", exe="/usr/libexec/mutter-x11-frames",
    )
    activity_run_create(
        account, kind="prc", started=started, finished=started + 3_600, duration=3_600,
        prc_name="gjs", exe="/usr/bin/gjs", application={
            "ident": "gjs:/usr/share/gnome-shell/extensions/ding@rastersoft.com/ding.js", "name": "ding.js",
        },
    )
    activity_run_create(
        account, kind="prc", started=started, finished=started + 60, duration=60,
        prc_name="gjs", exe="/usr/bin/gjs", application={"ident": "gjs:/apps/maps.js", "name": "Maps"},
    )

    report = ActivityEvent.objects.build_report(Account.objects.all(), date(2026, 10, 1), date(2026, 10, 2))
    timeline = build_usage_timeline(Account.objects.all(), started, started + 3_600)

    assert report.summary.screen_time == 3_600
    assert report.summary.application_count == 1
    assert [item.name for item in report.applications] == ["Maps"]
    assert [item.app_name for item in report.recent if item.kind == "application"] == ["Maps"]
    assert timeline.applications == {("Maps", "gjs:/apps/maps.js"): 60}
    assert timeline.people == {None: (3_600,)}
    assert account.activity_events.count() == 8
