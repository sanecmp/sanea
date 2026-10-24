"""Usage within an exact time window, based on completed activity runs."""

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
    people: dict[int | None, tuple[float, ...]]
    applications: dict[tuple[str, str], float]


def build_usage_timeline(
    accounts: QuerySet[Account], since: int, till: int, *, bucket_seconds: int = 3_600,
) -> UsageTimeline:
    """Estimate usage in ``[since, till)`` from runs completed by ``till``.

    Only final active durations are available, not the position of pauses within
    a run. Allocate each duration proportionally across its wall-clock interval,
    including the portion of a run that started before the requested window.
    Concurrent accounts and applications retain their separately recorded time.
    """

    if since < 0 or till <= since:
        raise ValueError("require 0 <= since < till")

    if bucket_seconds <= 0:
        raise ValueError("bucket_seconds must be positive")

    buckets = tuple(range(since, till, bucket_seconds))
    people: dict[int | None, list[float]] = defaultdict(lambda: [0.0] * len(buckets))

    application_totals: dict[tuple[str, ...], float] = defaultdict(float)
    application_labels: dict[tuple[str, ...], tuple[str, str]] = {}

    for start, end in _load_completed_runs(accounts, since, till):
        lower = max(start.timestamp, since)
        upper = end.timestamp
        elapsed = end.timestamp - start.timestamp

        if elapsed <= 0 or lower >= upper or not end.duration:
            continue

        rate = end.duration / elapsed

        if start.type == "prc_start":

            if is_desktop_component(start.prc_name, start.exe, start.app_id):
                continue

            key = start.get_application_key()
            application_totals[key] += rate * (upper - lower)
            application_labels[key] = (start.get_application_name() or start.prc_name or "", start.app_id or start.exe or "")
            continue

        person_usage = people[end.account.person_id]

        while lower < upper:
            index = (lower - since) // bucket_seconds
            bucket_end = min(buckets[index] + bucket_seconds, upper)
            person_usage[index] += rate * (bucket_end - lower)
            lower = bucket_end

    return UsageTimeline(
        buckets=buckets,
        people={person_id: tuple(durations) for person_id, durations in people.items()},
        applications={application_labels[key]: duration for key, duration in application_totals.items()},
    )


def _load_completed_runs(accounts: QuerySet[Account], since: int, till: int) -> tuple[tuple[ActivityEvent, ActivityEvent], ...]:
    endings = tuple(
        ActivityEvent.objects.filter(
            account__in=accounts,
            type__in=_START_TYPES,
            timestamp__gt=since,
            timestamp__lte=till,
            duration__isnull=False,
        ).select_related("account")
    )

    if not endings:
        return ()

    starts = {
        (event.account_id, event.seq, event.type): event
        for event in ActivityEvent.objects.filter(
            account__in=accounts,
            seq__in={event.run_ident for event in endings if event.run_ident is not None},
            type__in=_START_TYPES.values(),
        ).resolve_application_names()
    }
    return tuple(
        (start, end)
        for end in endings
        if (start := starts.get((end.account_id, end.run_ident, _START_TYPES[end.type]))) is not None
    )
