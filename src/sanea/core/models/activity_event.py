"""Received sanex activity events and report aggregation."""

from collections import defaultdict
from dataclasses import dataclass, replace
from datetime import date, datetime, time
from typing import Self, TYPE_CHECKING

from django.db import models
from django.db.models import OuterRef, QuerySet, Subquery
from django.db.models.functions import Coalesce
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from sanelib.protocol import Event as ClientEvent

from ...utils.applications import is_desktop_component
from .base import TimestampedModel

if TYPE_CHECKING:
    from .account import Account
    from .computer import Computer
    from .event_packet import EventPacket

_SESSION_START = "session_start"
_SESSION_END = "session_end"
_PROCESS_START = "prc_start"
_PROCESS_UPDATE = "prc_update"
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
    duration: int | None
    launches: int
    last_used: int
    app_id: str | None = None
    app_name: str | None = None

    @property
    def name(self) -> str:
        """Prefer the application label without losing technical process fields."""
        return self.app_name or self.prc_name or self.exe


@dataclass(frozen=True, slots=True)
class RecentActivity:
    """One completed session or a group of completed application runs."""

    kind: str
    account_id: int
    computer_id: int
    started: int
    finished: int
    duration: int
    prc_name: str | None = None
    exe: str | None = None
    app_name: str | None = None
    app_id: str | None = None
    launches: int = 1
    account_ids: tuple[int, ...] = ()


@dataclass(frozen=True, slots=True)
class ActivityReport:
    """Complete activity data required by the overview interface."""

    summary: ActivitySummary
    daily_screen_time: tuple[DailyScreenTime, ...]
    applications: tuple[ApplicationUsage, ...]
    recent: tuple[RecentActivity, ...]


class ActivityEventQuerySet(models.QuerySet):
    """Query and aggregate received activity events."""

    def resolve_application_names(self) -> Self:
        """Load the latest name correction for the same account, run and app ID."""
        updates = self.model.objects.filter(
            account_id=OuterRef("account_id"),
            run_ident=OuterRef("seq"),
            app_id=OuterRef("app_id"),
            type=_PROCESS_UPDATE,
            seq__gt=OuterRef("seq"),
        ).order_by("-seq")
        return self.annotate(resolved_app_name=Coalesce(Subquery(updates.values("app_name")[:1]), "app_name"))

    def build_report(
        self,
        accounts: QuerySet["Account"],
        since: date,
        till: date,
        *,
        recent_limit: int = 10,
    ) -> ActivityReport:
        """Build aggregates for local start dates in ``[since, till)``.

        Recent activity uses completion dates, with applications grouped by identity.
        Include up to ``recent_limit`` applications and completed sessions.
        """

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
        till: int | None = None,
    ) -> QuerySet["ActivityEvent"]:
        """Return enforcement failures for the selected computer and period."""
        failures = self.filter(type="enforcement_failed")

        if computer is not None:
            failures = failures.filter(account__computer=computer)

        if since is not None:
            failures = failures.filter(timestamp__gte=since)

        if till is not None:
            failures = failures.filter(timestamp__lt=till)

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
    app_id = models.CharField(
        verbose_name=_("Application identifier"), max_length=4096, null=True, blank=True,
        help_text=_("Recognized application identity, independent of its executable."),
    )
    app_name = models.CharField(
        verbose_name=_("Application name"), max_length=512, null=True, blank=True,
        help_text=_("Recognized application display name."),
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

    def get_application_key(self) -> tuple[str, ...]:
        """Group recognized applications by ID and unknown ones by raw name/path."""
        return (self.app_id,) if self.app_id else (self.prc_name or "", self.exe or "")

    def get_application_name(self) -> str | None:
        """Prefer a loaded name correction without changing the stored start event."""
        return getattr(self, "resolved_app_name", self.app_name)

    @classmethod
    def build_from_client_event(
        cls,
        account: "Account",
        packet: "EventPacket",
        event: ClientEvent,
    ) -> Self:
        """Build an unsaved database event from one validated protocol event."""
        application = getattr(event, "application", None)
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
            app_id=application.ident if application else None,
            app_name=application.name if application else None,
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
        process_starts = [
            event for event in starts
            if event.type == _PROCESS_START
            and not is_desktop_component(event.prc_name, event.exe, event.app_id)
        ]
        session_ends = ends[_SESSION_END]
        process_ends = ends[_PROCESS_END]

        daily_totals: dict[tuple[date, int | None], int] = defaultdict(int)

        for event in session_starts:
            end = session_ends.get((event.account_id, event.seq))

            if end is None:
                continue

            day = self._get_local_date(event)
            daily_totals[(day, event.account.person_id)] += end.duration or 0

        applications: dict[tuple[str, ...], dict[str, int]] = {}
        representatives: dict[tuple[str, ...], ActivityEvent] = {}

        for event in process_starts:
            key = event.get_application_key()
            representatives[key] = event
            usage = applications.setdefault(
                key,
                {"duration": 0, "launches": 0, "completed_launches": 0, "last_used": 0},
            )
            usage["launches"] += 1
            usage["last_used"] = max(usage["last_used"], event.timestamp)
            end = process_ends.get((event.account_id, event.seq))

            if end is not None:
                usage["duration"] += end.duration or 0
                usage["completed_launches"] += 1

        recent = self._build_recent()
        daily_screen_time = tuple(
            DailyScreenTime(day, person_id, duration)
            for (day, person_id), duration in sorted(daily_totals.items())
        )
        application_usage = tuple(
            sorted(
                (
                    ApplicationUsage(
                        representatives[key].prc_name or "",
                        representatives[key].exe or "",
                        values["duration"] if values["completed_launches"] else None,
                        values["launches"],
                        values["last_used"],
                        representatives[key].app_id,
                        representatives[key].get_application_name(),
                    )
                    for key, values in applications.items()
                ),
                key=lambda item: (-(item.duration or 0), -item.launches, item.prc_name, item.exe),
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

        if not self.accounts:
            return ()

        zone = timezone.get_current_timezone()
        lower = int(datetime.combine(self.since, time.min, zone).timestamp())
        upper = int(datetime.combine(self.till, time.min, zone).timestamp())
        return tuple(
            self.events.filter(
                account_id__in=[account.pk for account in self.accounts],
                timestamp__gte=lower,
                timestamp__lt=upper,
                type__in=(_SESSION_START, _PROCESS_START),
            ).resolve_application_names().select_related("account__computer", "account__person")
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

    def _build_recent(self) -> tuple[RecentActivity, ...]:

        if not self.accounts or not self.recent_limit:
            return ()

        zone = timezone.get_current_timezone()
        lower = int(datetime.combine(self.since, time.min, zone).timestamp())
        upper = int(datetime.combine(self.till, time.min, zone).timestamp())
        endings = tuple(self.events.filter(
            account_id__in=[account.pk for account in self.accounts],
            type__in=(_SESSION_END, _PROCESS_END),
            timestamp__gte=lower,
            timestamp__lt=upper,
            duration__isnull=False,
        ).order_by("timestamp", "seq"))
        starts = {
            (event.account_id, event.seq, event.type): event
            for event in self.events.filter(
                account_id__in=[account.pk for account in self.accounts],
                seq__in={event.run_ident for event in endings},
                type__in=(_SESSION_START, _PROCESS_START),
            ).resolve_application_names().select_related("account")
        }
        rows = []
        applications: dict[tuple[str, ...], RecentActivity] = {}

        unique_endings = {(event.account_id, event.run_ident, event.type): event for event in endings}

        for end in unique_endings.values():
            is_session = end.type == _SESSION_END
            start_type = _SESSION_START if is_session else _PROCESS_START
            event = starts.get((end.account_id, end.run_ident, start_type))

            if event is None:
                continue

            if not is_session and is_desktop_component(event.prc_name, event.exe, event.app_id):
                continue

            row = RecentActivity(
                kind="session" if is_session else "application",
                account_id=event.account_id,
                computer_id=event.account.computer_id,
                account_ids=(event.account_id,),
                started=event.timestamp,
                finished=end.timestamp,
                duration=end.duration or 0,
                prc_name=None if is_session else event.prc_name,
                exe=None if is_session else event.exe,
                app_name=None if is_session else event.get_application_name(),
                app_id=None if is_session else event.app_id,
            )

            if is_session:
                rows.append(row)
                continue

            key = event.get_application_key()
            previous = applications.get(key)

            if previous is not None:
                row = replace(
                    row,
                    duration=previous.duration + row.duration,
                    launches=previous.launches + 1,
                    account_ids=tuple(sorted({*previous.account_ids, event.account_id})),
                )

            applications[key] = row

        rows.extend(applications.values())
        rows.sort(key=lambda item: (item.finished, item.started, item.account_id), reverse=True)
        counts: dict[str, int] = defaultdict(int)
        recent = []

        for item in rows:

            if counts[item.kind] < self.recent_limit:
                recent.append(item)
                counts[item.kind] += 1

        return tuple(recent)

    @staticmethod
    def _get_local_date(event: ActivityEvent) -> date:
        return datetime.fromtimestamp(event.timestamp, timezone.get_current_timezone()).date()
