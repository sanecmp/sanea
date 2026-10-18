"""Tests for rolling-window usage aggregation."""

from collections.abc import Callable

import pytest

from sanea.core.models import Account, Computer, Person
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
    activity_run_create(first, started=since - 3_600, finished=since + 3_600, duration=3_600)
    activity_run_create(second, started=since + 1_800, finished=since + 5_400, duration=3_600)
    activity_run_create(guest, started=since + 3_600, finished=since + 7_200, duration=1_800)
    activity_run_create(excluded, started=since, finished=since + 7_200, duration=7_200)
    excluded.collect = False
    excluded.save(update_fields=("collect",))
    activity_run_create(first, kind="prc", started=since - 3_600, finished=since + 3_600, duration=3_600)
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
        pytest.param(0, 7_201, 3_600, 0, id="ends-after-upper-bound"),
        pytest.param(7_200, 7_201, 1, 0, id="starts-at-upper-bound"),
        pytest.param(0, None, 0, 0, id="ongoing"),
        pytest.param(3_600, 3_600, 100, 0, id="no-wall-clock-interval"),
        pytest.param(3_600, 1_800, 100, 0, id="clock-went-backwards"),
        pytest.param(0, 3_600, 0, 0, id="zero-active-time"),
    ],
)
def test_timeline_uses_only_final_durations_completed_within_bounds(
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


@pytest.mark.parametrize(("since", "till"), [(100, 100), (101, 100), (-1, 100)])
def test_timeline_rejects_invalid_bounds(since: int, till: int) -> None:

    with pytest.raises(ValueError, match="require 0 <= since < till"):
        build_usage_timeline(Account.objects.none(), since, till)


def test_timeline_can_group_longer_periods_without_losing_partial_intervals(activity_run_create: Callable[..., None]) -> None:
    since = 1_790_000_000
    computer = Computer.objects.create(hostname="synthetic-desktop", status="allowed")
    account = Account.objects.create(computer=computer, uid=1001, collect=True)
    activity_run_create(account, started=since + 43_200, finished=since + 129_600, duration=7_200)

    timeline = build_usage_timeline(Account.objects.all(), since, since + 129_600, bucket_seconds=86_400)

    assert timeline.buckets == (since, since + 86_400)
    assert timeline.people[None] == (3_600, 3_600)


@pytest.mark.parametrize("bucket_seconds", [0, -1])
def test_timeline_rejects_nonpositive_chart_intervals(bucket_seconds: int) -> None:

    with pytest.raises(ValueError, match="bucket_seconds must be positive"):
        build_usage_timeline(Account.objects.none(), 100, 200, bucket_seconds=bucket_seconds)
