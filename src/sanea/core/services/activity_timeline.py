"""Usage within an exact time window, based on completed activity runs."""

from bisect import bisect_right
from collections import defaultdict
from dataclasses import dataclass

from django.db.models import QuerySet

from ...utils.applications import is_desktop_component
from ..models import Account, ActivityEvent


_START_TYPES = {"session_end": "session_start", "prc_end": "prc_start"}


@dataclass(frozen=True, slots=True)
class UsageTimeline:
    """Screen time by person and total time by application identity."""

    buckets: tuple[int, ...]
    people: dict[int | None, tuple[int, ...]]
    applications: dict[tuple[str, str], int]


def build_usage_timeline(
    accounts: QuerySet[Account], since: int, till: int, *, bucket_seconds: int = 3_600,
    bucket_boundaries: tuple[int, ...] | None = None,
) -> UsageTimeline:
    """Sum recorded usage intervals intersecting ``[since, till)``.

    Only received completed runs with known intervals contribute to the timeline.
    A run may end after the requested window; its actual intervals determine
    which portion belongs to the window. Unknown historical intervals are not
    reconstructed from the final duration or the login session's start time.
    Concurrent accounts and applications retain their separately recorded time.
    Explicit ``bucket_boundaries`` support local calendar days of varying lengths.
    Their first interval must contain ``since`` and the last boundary must be
    ``till``. Otherwise, use uniform intervals of ``bucket_seconds``.
    """

    if since < 0 or till <= since:
        raise ValueError("require 0 <= since < till")

    if bucket_seconds <= 0:
        raise ValueError("bucket_seconds must be positive")

    if bucket_boundaries is None:
        bucket_boundaries = (*range(since, till, bucket_seconds), till)

    if (
        len(bucket_boundaries) < 2
        or not (bucket_boundaries[0] <= since < bucket_boundaries[1])
        or bucket_boundaries[-1] != till
        or any(lower >= upper for lower, upper in zip(bucket_boundaries, bucket_boundaries[1:]))
    ):
        raise ValueError("bucket boundaries must increase, contain since in the first interval and end at till")

    buckets = bucket_boundaries[:-1]
    people: dict[int | None, list[int]] = defaultdict(lambda: [0] * len(buckets))

    application_totals: dict[tuple[str, ...], int] = defaultdict(int)
    application_labels: dict[tuple[str, ...], tuple[str, str]] = {}

    for start, end in _load_completed_runs(accounts):
        segments = []

        for interval in end.intervals:
            lower = max(interval["timestamp"] - interval["duration"], since)
            upper = min(interval["timestamp"], till)

            if lower < upper:
                segments.append((lower, upper))

        if not segments:
            continue

        if start.type == "prc_start":

            if is_desktop_component(start.prc_name, start.exe, start.app_id):
                continue

            key = start.get_application_key()
            application_totals[key] += sum(upper - lower for lower, upper in segments)
            application_labels[key] = (start.get_application_name() or start.prc_name or "", start.app_id or start.exe or "")
            continue

        person_usage = people[end.account.person_id]

        for lower, upper in segments:
            index = bisect_right(bucket_boundaries, lower) - 1

            while lower < upper:
                bucket_end = min(bucket_boundaries[index + 1], upper)
                person_usage[index] += bucket_end - lower
                lower = bucket_end
                index += 1

    return UsageTimeline(
        buckets=buckets,
        people={person_id: tuple(durations) for person_id, durations in people.items()},
        applications={application_labels[key]: duration for key, duration in application_totals.items()},
    )


def _load_completed_runs(accounts: QuerySet[Account]) -> tuple[tuple[ActivityEvent, ActivityEvent], ...]:
    endings: dict[tuple[int, int | None, str], ActivityEvent] = {}

    for event in ActivityEvent.objects.filter(
        account__in=accounts,
        type__in=_START_TYPES,
        intervals__isnull=False,
        duration__isnull=False,
    ).select_related("account"):
        key = event.account_id, event.run_ident, event.type
        previous = endings.get(key)

        # A replay after an interrupted state save must not duplicate or replace
        # a more complete recorded history with a stale, shorter counter.
        if previous is None or (event.duration, event.seq) > (previous.duration, previous.seq):
            endings[key] = event

    if not endings:
        return ()

    starts = {
        (event.account_id, event.seq, event.type): event
        for event in ActivityEvent.objects.filter(
            account__in=accounts,
            seq__in={event.run_ident for event in endings.values() if event.run_ident is not None},
            type__in=_START_TYPES.values(),
        ).resolve_application_names()
    }
    return tuple(
        (start, end)
        for end in endings.values()
        if (start := starts.get((end.account_id, end.run_ident, _START_TYPES[end.type]))) is not None
    )
