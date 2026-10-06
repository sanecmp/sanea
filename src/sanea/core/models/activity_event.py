"""Received sanex activity events and report aggregation."""

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime, time
from zoneinfo import ZoneInfo
from typing import Self, TYPE_CHECKING

from django.db import models
from django.db.models import Q, QuerySet
from django.utils.translation import gettext_lazy as _
from sanelib.protocol import Event as ClientEvent

from .base import TimestampedModel

if TYPE_CHECKING:
    from .account import Account
    from .computer import Computer
    from .event_packet import EventPacket

_SESSION_START = "session_start"
_SESSION_END = "session_end"
_PROCESS_START = "prc_start"
_PROCESS_END = "prc_end"


@dataclass(frozen=True, slots=True)
class ActivitySummary:
    """Top-level activity totals for one selected scope."""

    screen_time: int
    session_count: int
    application_count: int


@dataclass(frozen=True, slots=True)
class DailyScreenTime:
    """Completed session duration assigned to one local start date."""

    day: date
    person_id: int | None
    duration: int


@dataclass(frozen=True, slots=True)
class ApplicationUsage:
    """Aggregated launches and completed duration for one application identity."""

    prc_name: str
    exe: str
    duration: int
    launches: int
    last_used: int


@dataclass(frozen=True, slots=True)
class RecentActivity:
    """One completed session or application run for display."""

    kind: str
    account_id: int
    computer_id: int
    started: int
    finished: int
    duration: int
    prc_name: str | None = None
    exe: str | None = None


@dataclass(frozen=True, slots=True)
class ActivityReport:
    """Complete activity data required by the overview interface."""

    summary: ActivitySummary
    daily_screen_time: tuple[DailyScreenTime, ...]
    applications: tuple[ApplicationUsage, ...]
    recent: tuple[RecentActivity, ...]


class ActivityEventQuerySet(models.QuerySet):
    """Query and aggregate received activity events."""

    def build_report(
        self,
        accounts: QuerySet["Account"],
        since: date,
        till: date,
        *,
        recent_limit: int = 10,
    ) -> ActivityReport:
        """Build activity aggregates for local start dates in ``[since, till)``."""

        if till <= since:
            raise ValueError("till must be later than since")

        if recent_limit < 0:
            raise ValueError("recent_limit must not be negative")

        return _ActivityReportBuilder(
            self,
            tuple(accounts.select_related("computer", "person")),
            since,
            till,
            recent_limit,
        ).build()

    def get_enforcement_failures(
        self,
        *,
        computer: "Computer | None"=None,
        since: int | None = None,
    ) -> QuerySet["ActivityEvent"]:
        """Return enforcement failures for the selected computer and period."""
        failures = self.filter(type="enforcement_failed")

        if computer is not None:
            failures = failures.filter(account__computer=computer)

        if since is not None:
            failures = failures.filter(timestamp__gte=since)

        return failures.select_related(
            "account__computer",
            "account__person",
        ).order_by("-timestamp", "-pk")


class ActivityEvent(TimestampedModel):
    """One validated session, process or enforcement event."""

    account = models.ForeignKey(
        "Account",
        verbose_name=_("Account"),
        on_delete=models.CASCADE,
        related_name="activity_events",
        help_text=_("Local account to which this event belongs."),
    )
    packet = models.ForeignKey(
        "EventPacket",
        verbose_name=_("Event packet"),
        on_delete=models.CASCADE,
        related_name="events",
        help_text=_("Received packet containing this event."),
    )
    seq = models.PositiveBigIntegerField(
        verbose_name=_("Sequence"),
        help_text=_("Monotonic event number within the local account."),
    )
    type = models.CharField(
        verbose_name=_("Type"),
        max_length=32,
        help_text=_("Protocol event type."),
    )
    timestamp = models.PositiveBigIntegerField(
        verbose_name=_("Timestamp"),
        help_text=_("Unix timestamp reported by sanex in whole seconds."),
    )
    run_ident = models.PositiveBigIntegerField(
        verbose_name=_("Run identifier"),
        null=True,
        blank=True,
        help_text=_("Sequence number of the related session or process start."),
    )
    sess_ident = models.TextField(
        verbose_name=_("Session identifier"),
        null=True,
        blank=True,
        help_text=_("Local logind session identifier."),
    )
    duration = models.PositiveBigIntegerField(
        verbose_name=_("Duration"),
        null=True,
        blank=True,
        help_text=_("Observed active duration in seconds."),
    )
    prc_name = models.TextField(
        verbose_name=_("Process name"),
        null=True,
        blank=True,
        help_text=_("Observed user application process name."),
    )
    exe = models.TextField(
        verbose_name=_("Executable"),
        null=True,
        blank=True,
        help_text=_("Resolved executable path without command-line arguments."),
    )
    rule_ident = models.PositiveBigIntegerField(
        verbose_name=_("Rule identifier"),
        null=True,
        blank=True,
        help_text=_("Application rule involved in an enforcement failure."),
    )
    wnd_ident = models.PositiveBigIntegerField(
        verbose_name=_("Window identifier"),
        null=True,
        blank=True,
        help_text=_("Local window identifier involved in an enforcement failure."),
    )
    reason = models.CharField(
        verbose_name=_("Reason"),
        max_length=64,
        null=True,
        blank=True,
        help_text=_("Protocol reason for an enforcement failure."),
    )
    meta = models.JSONField(
        verbose_name=_("Metadata"),
        default=dict,
        help_text=_("Type-specific event metadata."),
    )

    objects = ActivityEventQuerySet.as_manager()

    class Meta:
        verbose_name = _("Activity event")
        verbose_name_plural = _("Activity events")
        ordering = ("account", "seq")
        constraints = [
            models.UniqueConstraint(
                fields=("account", "seq"),
                name="core_activityevent_account_seq_unique",
            ),
        ]
        indexes = [
            models.Index(
                fields=("account", "timestamp"),
                name="core_event_account_time_idx",
            ),
            models.Index(
                fields=("account", "type", "timestamp"),
                name="core_event_account_type_idx",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.type} #{self.seq} ({self.account_id})"

    @classmethod
    def build_from_client_event(
        cls,
        account: "Account",
        packet: "EventPacket",
        event: ClientEvent,
    ) -> Self:
        """Build an unsaved database event from one validated protocol event."""
        return cls(
            account=account,
            packet=packet,
            seq=event.seq,
            type=event.type.value,
            timestamp=event.timestamp,
            run_ident=getattr(event, "run_ident", None),
            sess_ident=getattr(event, "sess_ident", None),
            duration=getattr(event, "duration", None),
            prc_name=getattr(event, "prc_name", None),
            exe=getattr(event, "exe", None),
            rule_ident=getattr(event, "rule_ident", None),
            wnd_ident=getattr(event, "wnd_ident", None),
            reason=getattr(event, "reason", None),
            meta=event.meta.model_dump(mode="json"),
        )


class _ActivityReportBuilder:
    """Build one report while retaining its selected scope and lookup state."""

    def __init__(
        self,
        events: ActivityEventQuerySet,
        accounts: tuple["Account", ...],
        since: date,
        till: date,
        recent_limit: int,
    ) -> None:
        self.events = events
        self.accounts = accounts
        self.since = since
        self.till = till
        self.recent_limit = recent_limit

    def build(self) -> ActivityReport:
        """Load the selected runs once and produce every report section."""
        starts = self._load_starts()
        ends = self._load_ends(starts)
        session_starts = [event for event in starts if event.type == _SESSION_START]
        process_starts = [event for event in starts if event.type == _PROCESS_START]
        session_ends = ends[_SESSION_END]
        process_ends = ends[_PROCESS_END]

        daily_totals: dict[tuple[date, int | None], int] = defaultdict(int)

        for event in session_starts:
            end = session_ends.get((event.account_id, event.seq))

            if end is None:
                continue

            day = self._get_local_date(event)
            daily_totals[(day, event.account.person_id)] += end.duration or 0

        applications: dict[tuple[str, str], dict[str, int]] = {}

        for event in process_starts:
            key = (event.prc_name or "", event.exe or "")
            usage = applications.setdefault(
                key,
                {"duration": 0, "launches": 0, "last_used": 0},
            )
            usage["launches"] += 1
            usage["last_used"] = max(usage["last_used"], event.timestamp)
            end = process_ends.get((event.account_id, event.seq))

            if end is not None:
                usage["duration"] += end.duration or 0

        recent = self._build_recent(starts, session_ends, process_ends)
        daily_screen_time = tuple(
            DailyScreenTime(day, person_id, duration)
            for (day, person_id), duration in sorted(daily_totals.items())
        )
        application_usage = tuple(
            sorted(
                (
                    ApplicationUsage(
                        prc_name,
                        exe,
                        values["duration"],
                        values["launches"],
                        values["last_used"],
                    )
                    for (prc_name, exe), values in applications.items()
                ),
                key=lambda item: (-item.duration, -item.launches, item.prc_name, item.exe),
            )
        )
        summary = ActivitySummary(
            screen_time=sum(item.duration for item in daily_screen_time),
            session_count=len(session_starts),
            application_count=len(application_usage),
        )
        return ActivityReport(
            summary=summary,
            daily_screen_time=daily_screen_time,
            applications=application_usage,
            recent=recent,
        )

    def _load_starts(self) -> tuple[ActivityEvent, ...]:
        accounts = self.accounts
        condition = Q(pk__in=())

        for account in accounts:
            zone = ZoneInfo(account.computer.timezone)
            lower = int(datetime.combine(self.since, time.min, zone).timestamp())
            upper = int(datetime.combine(self.till, time.min, zone).timestamp())
            condition |= Q(
                account_id=account.pk,
                timestamp__gte=lower,
                timestamp__lt=upper,
            )

        if not accounts:
            return ()

        return tuple(
            self.events.filter(
                condition,
                type__in=(_SESSION_START, _PROCESS_START),
            ).select_related("account__computer", "account__person")
        )

    def _load_ends(
        self,
        starts: tuple[ActivityEvent, ...],
    ) -> dict[str, dict[tuple[int, int], ActivityEvent]]:
        result: dict[str, dict[tuple[int, int], ActivityEvent]] = {
            _SESSION_END: {},
            _PROCESS_END: {},
        }
        starts_by_account: dict[int, list[int]] = defaultdict(list)

        for event in starts:
            starts_by_account[event.account_id].append(event.seq)

        for account_id, run_idents in starts_by_account.items():
            endings = self.events.filter(
                account_id=account_id,
                run_ident__in=run_idents,
                type__in=(_SESSION_END, _PROCESS_END),
            )

            for event in endings:
                run_ident = event.run_ident

                if run_ident is not None:
                    result[event.type][(account_id, run_ident)] = event

        return result

    def _build_recent(
        self,
        starts: Iterable[ActivityEvent],
        session_ends: dict[tuple[int, int], ActivityEvent],
        process_ends: dict[tuple[int, int], ActivityEvent],
    ) -> tuple[RecentActivity, ...]:
        rows = []
        append_row = rows.append

        for event in starts:
            is_session = event.type == _SESSION_START
            endings = session_ends if is_session else process_ends
            end = endings.get((event.account_id, event.seq))

            if end is None:
                continue

            append_row(
                RecentActivity(
                    kind="session" if is_session else "application",
                    account_id=event.account_id,
                    computer_id=event.account.computer_id,
                    started=event.timestamp,
                    finished=end.timestamp,
                    duration=end.duration or 0,
                    prc_name=None if is_session else event.prc_name,
                    exe=None if is_session else event.exe,
                )
            )

        rows.sort(key=lambda item: (item.started, item.account_id), reverse=True)
        return tuple(rows[: self.recent_limit])

    @staticmethod
    def _get_local_date(event: ActivityEvent) -> date:
        zone = ZoneInfo(event.account.computer.timezone)
        return datetime.fromtimestamp(event.timestamp, zone).date()
