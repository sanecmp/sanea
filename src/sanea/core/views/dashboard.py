"""Parent dashboard with recent screen time and application usage."""

from collections.abc import Callable
from datetime import datetime, time, timedelta

from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone
from django.utils.formats import date_format
from django.utils.translation import gettext_lazy as _

from ..forms import DashboardFilterForm
from ..models import Person
from ..services.activity_timeline import build_usage_timeline
from .base import ManagedView


_CHART_COLORS = ("#bd4a22", "#71886b", "#d89138", "#607d9b", "#9a6c9e", "#a47750")


class _DashboardPresenter:
    """Prepare both usage charts for a shared person and rolling period."""

    @staticmethod
    def build_usage_context(request: HttpRequest) -> dict[str, object]:
        """Build both charts and their accessible textual summaries."""
        data = request.GET.copy()
        data.setdefault("period", DashboardFilterForm.PERIOD_48_HOURS)
        form = DashboardFilterForm(data)
        valid = form.is_valid()
        context = {
            "dashboard_url": reverse("core:dashboard"),
            "dashboard_filter": form,
            "usage_valid": valid,
        }

        if not valid:
            return context

        hour_count = form.get_hour_count()
        hourly = hour_count <= 48
        since, till = form.get_timestamp_range(timezone.now())
        zone = timezone.get_current_timezone()
        since_moment = datetime.fromtimestamp(since, zone)
        till_moment = datetime.fromtimestamp(till, zone)

        if hourly:
            bucket_boundaries = (*range(since, till, 3_600), till)

        else:
            day_count = (till_moment.date() - since_moment.date()).days
            bucket_boundaries = tuple(
                int(datetime.combine(since_moment.date() + timedelta(days=offset), time.min, zone).timestamp())
                for offset in range(day_count + 1)
            )

            if bucket_boundaries[-1] < till:
                bucket_boundaries += (till,)

        accounts = form.get_accounts()
        timeline = build_usage_timeline(accounts, since, till, bucket_boundaries=bucket_boundaries)
        all_people = list(Person.objects.values_list("pk", "name"))
        selected_person = form.cleaned_data["person"]
        people = {
            person_id: name for person_id, name in all_people
            if selected_person is None or person_id == selected_person.pk
        }
        colors = {person_id: _CHART_COLORS[index % len(_CHART_COLORS)] for index, (person_id, name) in enumerate(all_people)}

        if None in timeline.people:
            people[None] = _("No user")

        datasets = []
        people_totals = []

        for person_id, name in people.items():
            durations = timeline.people.get(person_id, (0,) * len(timeline.buckets))
            color = colors.get(person_id, _CHART_COLORS[-1])
            datasets.append(
                {
                    "label": f"{name}",
                    "data": [round(duration, 2) for duration in durations],
                    "backgroundColor": color,
                    "borderColor": color,
                    "borderWidth": 1,
                    "borderRadius": 3,
                }
            )
            people_totals.append({"name": name, "duration": round(sum(durations))})

        applications = sorted(timeline.applications.items(), key=lambda item: (-item[1], item[0]))[:10]
        application_labels = [name or executable for (name, executable), duration in applications]
        moments = [datetime.fromtimestamp(bucket, zone) for bucket in timeline.buckets]
        tooltip_titles = []

        for bucket, bucket_end in zip(bucket_boundaries, bucket_boundaries[1:]):
            lower = datetime.fromtimestamp(max(bucket, since), zone)
            upper = datetime.fromtimestamp(bucket_end, zone)
            moment_format = "%d.%m.%Y %H:%M %z" if lower.utcoffset() != upper.utcoffset() else "%d.%m.%Y %H:%M"
            tooltip_titles.append(f"{lower:{moment_format}} — {upper:{moment_format}}")

        hour_unit = _("h")
        minute_unit = _("min")
        units = {"hour": f"{hour_unit}", "minute": f"{minute_unit}"}
        return {
            **context,
            "usage_since": since_moment,
            "usage_till": till_moment,
            "usage_timezone": timezone.get_current_timezone_name(),
            "usage_has_accounts": accounts.exists(),
            "usage_has_screen_time": bool(timeline.people),
            "usage_granularity": _("Completed sessions by hour") if hourly else _("Completed sessions by day"),
            "usage_people": people_totals,
            "usage_applications": [
                {"name": name or executable, "exe": executable, "duration": round(duration)}
                for (name, executable), duration in applications
            ],
            "people_chart": {
                "labels": [
                    [date_format(moment, "d.m"), date_format(moment, "H:i")]
                    for moment in moments
                ] if hourly else [date_format(moment, "d.m") for moment in moments],
                "datasets": datasets,
                "units": units,
                "tooltipTitles": tooltip_titles,
            },
            "applications_chart": {
                "labels": application_labels,
                "datasets": [{
                    "label": f"{_("Time")}",
                    "data": [round(duration, 2) for identity, duration in applications],
                    "backgroundColor": _CHART_COLORS[0],
                    "borderRadius": 4,
                }],
                "indexAxis": "y",
                "units": units,
            },
        }


class DashboardView(ManagedView):
    """Render a recent-usage overview without duplicating navigation."""

    def get_ajax_handlers(self) -> dict[str, Callable[..., HttpResponse]]:
        """Return the independently refreshable usage handler."""
        return {"dashboard-filter": self.render_area, "dashboard-usage": self.render_usage}

    def dispatch(self, request: HttpRequest, **kwargs: object) -> HttpResponse:
        """Render the complete dashboard."""
        context = {"page_title": _("Dashboard"), **_DashboardPresenter.build_usage_context(request)}
        return render(request, "sanea/dashboard.html", context)

    def render_usage(self, request: HttpRequest, **kwargs: object) -> HttpResponse:
        """Refresh the rolling window without replacing page navigation."""
        return render(request, "sanea/dashboard/_usage.html", _DashboardPresenter.build_usage_context(request))

    def render_area(self, request: HttpRequest, **kwargs: object) -> HttpResponse:
        """Replace submitted filters and charts with the validated selection."""
        return render(request, "sanea/dashboard/_area.html", _DashboardPresenter.build_usage_context(request))


dashboard = DashboardView().as_view()
