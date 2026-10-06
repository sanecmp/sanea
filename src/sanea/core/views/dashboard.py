"""Parent dashboard view."""

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
from collections.abc import Callable

from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone
from django.utils.formats import date_format
from django.utils.translation import gettext_lazy as _
from django.db.models import QuerySet

from ..forms import ActivityFilterForm
from ..models import Account, ActivityEvent, ClientCommand, Computer, Person
from .base import ManagedView
from ..models.activity_event import ActivityReport


_CHART_COLORS = (
    "#bd4a22",
    "#71886b",
    "#d89138",
    "#607d9b",
    "#9a6c9e",
    "#a47750",
)


class _DashboardPresenter:
    """Build the dashboard context from one request and selected activity scope."""

    def __init__(self, request: HttpRequest) -> None:
        self.request = request

    def build_context(self) -> dict[str, object]:
        """Build the complete page context."""
        return {
            "page_title": _("Dashboard"),
            "summary_cards": self.build_domain_cards(),
            **self.build_system_status_context(),
            **self.build_activity_context(),
        }

    def build_domain_cards(self) -> tuple[dict[str, object], ...]:
        """Build navigation cards for registered domain entities."""
        return (
            {
                "label": _("People"),
                "value": Person.objects.count(),
                "icon": "people",
                "url": reverse("core:people"),
            },
            {
                "label": _("Computers"),
                "value": Computer.objects.count(),
                "icon": "computers",
                "url": reverse("core:computers"),
            },
            {
                "label": _("Accounts"),
                "value": Account.objects.count(),
                "icon": "accounts",
                "url": reverse("core:accounts"),
            },
        )

    @staticmethod
    def build_system_status_context() -> dict[str, object]:
        """Build the operational computer and command summary."""
        computers_url = reverse("core:computers")
        return {
            "connection_counts": Computer.count_connection_statuses(),
            "command_counts": ClientCommand.count_operational_statuses(),
            "waiting_config_count": Computer.count_waiting_configs(),
            "computers_url": computers_url,
            "waiting_configs_url": f"{computers_url}?config_delivery=waiting#computer-list",
            "pending_commands_url": f"{computers_url}?command_status=pending#command-history",
            "failed_commands_url": f"{computers_url}?command_status=failed#command-history",
            "issues_url": reverse("core:issues"),
            "dashboard_url": reverse("core:dashboard"),
        }

    def build_activity_context(self) -> dict[str, object]:
        """Validate activity filters and prepare report presentation data."""
        request = self.request
        data = request.GET or {"period": ActivityFilterForm.PERIOD_TODAY}
        form = ActivityFilterForm(data)
        context: dict[str, object] = {
            "activity_filter": form,
            "activity_url": reverse("core:dashboard"),
            "activity_report": None,
        }

        if not form.is_valid():
            return context

        today = timezone.localdate()
        since, till = form.get_date_range(today)
        accounts = form.get_accounts()
        report = ActivityEvent.objects.build_report(accounts, since, till)
        context.update(
            {
                "activity_report": report,
                "activity_since": since,
                "activity_till": till - timedelta(days=1),
                "activity_chart": self.build_chart(report, accounts, since, till),
                "recent_activity": self.build_recent_activity(report),
            }
        )
        return context

    def build_chart(self, report: ActivityReport, accounts: QuerySet[Account], since: date, till: date) -> dict[str, object]:
        """Build serializable stacked-bar data with explicit empty days."""
        days = []
        current = since

        while current < till:
            days.append(current)
            current += timedelta(days=1)

        people = {
            account.person_id: account.person.name
            if account.person_id
            else _("No user")
            for account in accounts.select_related("person")
        }
        people.update(
            {
                item.person_id: _("No user")
                for item in report.daily_screen_time
                if item.person_id is None
            }
        )
        totals = {
            (item.day, item.person_id): item.duration
            for item in report.daily_screen_time
        }
        datasets = []

        for index, (person_id, label) in enumerate(
            sorted(people.items(), key=lambda item: f"{item[1]}")
        ):
            color = _CHART_COLORS[index % len(_CHART_COLORS)]
            datasets.append(
                {
                    "label": f"{label}",
                    "data": [totals.get((day, person_id), 0) for day in days],
                    "backgroundColor": color,
                    "borderColor": color,
                    "borderWidth": 1,
                    "borderRadius": 4,
                }
            )

        hour_unit = _("h")
        minute_unit = _("min")
        return {
            "labels": [date_format(day, "SHORT_DATE_FORMAT") for day in days],
            "datasets": datasets,
            "units": {"hour": f"{hour_unit}", "minute": f"{minute_unit}"},
        }

    @staticmethod
    def build_recent_activity(report: ActivityReport) -> tuple[dict[str, object], ...]:
        """Resolve recent rows to human-readable account and computer labels."""
        account_ids = {item.account_id for item in report.recent}
        accounts = {
            account.pk: account
            for account in Account.objects.filter(pk__in=account_ids).select_related(
                "computer"
            )
        }
        rows = []
        add_row = rows.append

        for item in report.recent:
            account = accounts[item.account_id]
            computer = account.computer
            zone = ZoneInfo(computer.timezone)
            add_row(
                {
                    "kind": _("Session")
                    if item.kind == "session"
                    else _("Application"),
                    "name": item.prc_name or item.exe or _("User session"),
                    "account": account,
                    "computer": computer,
                    "started": datetime.fromtimestamp(item.started, zone),
                    "duration": item.duration,
                }
            )

        return tuple(rows)


class DashboardView(ManagedView):
    """Render registered-domain totals and filterable operational summaries."""

    def get_ajax_handlers(self) -> dict[str, Callable[..., HttpResponse]]:
        """Return independently refreshable dashboard handlers."""
        return {
            "activity-filter": self.render_activity,
            "system-status": self.render_system_status,
        }

    def dispatch(self, request: HttpRequest, **kwargs: object) -> HttpResponse:
        """Render the complete dashboard."""
        context = _DashboardPresenter(request).build_context()
        return render(request, "sanea/dashboard.html", context)

    def render_system_status(
        self,
        request: HttpRequest,
        **kwargs: object,
    ) -> HttpResponse:
        """Render the independently refreshable operational summary."""
        context = _DashboardPresenter.build_system_status_context()
        return render(request, "sanea/dashboard/_system_status.html", context)

    def render_activity(self, request: HttpRequest, **kwargs: object) -> HttpResponse:
        """Render the independently refreshable activity fragment."""
        context = _DashboardPresenter(request).build_activity_context()
        return render(request, "sanea/dashboard/_activity.html", context)


dashboard = DashboardView().as_view()
