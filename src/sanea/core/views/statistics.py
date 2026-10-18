"""Dedicated activity statistics and application-usage view."""

from collections.abc import Callable
from datetime import date, datetime, timedelta

from django.db.models import Max, QuerySet
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone
from django.utils.formats import date_format
from django.utils.translation import gettext_lazy as _

from ..forms import ActivityFilterForm
from ..models import Account, ActivityEvent, EventPacket
from ..models.activity_event import ActivityReport
from .base import ManagedView


_CHART_COLORS = (
    "#bd4a22",
    "#71886b",
    "#d89138",
    "#607d9b",
    "#9a6c9e",
    "#a47750",
)


class _StatisticsPresenter:
    """Prepare activity reports for the selected accounts and period."""

    def __init__(self, request: HttpRequest) -> None:
        self.request = request

    def build_context(self) -> dict[str, object]:
        """Build the complete statistics page context."""
        return {
            "page_title": _("Statistics"),
            **self.build_activity_context(),
        }

    def build_activity_context(self) -> dict[str, object]:
        """Validate activity filters and prepare report presentation data."""
        request = self.request
        data = request.GET or {"period": ActivityFilterForm.PERIOD_TODAY}
        form = ActivityFilterForm(data)
        context: dict[str, object] = {
            "activity_filter": form,
            "activity_url": reverse("core:statistics"),
            "activity_report": None,
        }

        if not form.is_valid():
            return context

        today = timezone.localdate()
        since, till = form.get_date_range(today)
        accounts = form.get_accounts()
        report = ActivityEvent.objects.build_report(accounts, since, till)
        recent = self.build_recent_activity(report)
        selected_kind = request.GET.get("activity_kind", "application")

        if selected_kind not in recent:
            selected_kind = "application"

        tabs = []

        for kind, label, empty_label in (
            ("application", _("Applications"), _("No completed application runs for this period.")),
            ("session", _("Sessions"), _("No completed sessions for this period.")),
        ):
            query = request.GET.copy()
            query.setdefault("period", form.cleaned_data["period"])
            query["activity_kind"] = kind
            tabs.append({
                "kind": kind,
                "label": label,
                "empty_label": empty_label,
                "items": recent[kind],
                "active": kind == selected_kind,
                "url": f"{context["activity_url"]}?{query.urlencode()}",
            })

        context.update(
            {
                "activity_report": report,
                "activity_has_accounts": accounts.exists(),
                "activity_last_received": EventPacket.objects.filter(
                    account__in=accounts
                ).aggregate(latest=Max("created"))["latest"],
                "activity_since": since,
                "activity_till": till - timedelta(days=1),
                "activity_timezone": timezone.get_current_timezone_name(),
                "activity_chart": self.build_chart(report, accounts, since, till),
                "recent_activity_tabs": tabs,
                "activity_kind": selected_kind,
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
    def build_recent_activity(report: ActivityReport) -> dict[str, list[dict[str, object]]]:
        """Group recent applications and sessions with familiar account labels."""
        account_ids = {item.account_id for item in report.recent}
        accounts = {
            account.pk: account
            for account in Account.objects.filter(pk__in=account_ids).select_related(
                "computer"
            )
        }
        rows: dict[str, list[dict[str, object]]] = {"application": [], "session": []}
        zone = timezone.get_current_timezone()

        for item in report.recent:
            account = accounts[item.account_id]
            computer = account.computer
            account_name = account.name or account.login
            is_session = item.kind == "session"
            rows[item.kind].append(
                {
                    "name": account_name if is_session else item.app_name or item.prc_name or item.exe,
                    "details": computer.get_display_name() if is_session else f"{account_name} · {computer.get_display_name()}",
                    "started": datetime.fromtimestamp(item.started, zone),
                    "duration": item.duration,
                }
            )

        return rows


class StatisticsView(ManagedView):
    """Render activity statistics with progressively enhanced filters."""

    def get_ajax_handlers(self) -> dict[str, Callable[..., HttpResponse]]:
        """Return the independently refreshable activity handler."""
        return {"activity-filter": self.render_activity}

    def dispatch(self, request: HttpRequest, **kwargs: object) -> HttpResponse:
        """Render the complete statistics page."""
        context = _StatisticsPresenter(request).build_context()
        return render(request, "sanea/statistics.html", context)

    def render_activity(self, request: HttpRequest, **kwargs: object) -> HttpResponse:
        """Render filtered activity without replacing page navigation."""
        context = _StatisticsPresenter(request).build_activity_context()
        return render(request, "sanea/statistics/_activity.html", context)


statistics = StatisticsView().as_view()
