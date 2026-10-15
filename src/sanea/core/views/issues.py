"""Reported client issues and diagnostic logs."""

import json
from collections.abc import Iterable
from datetime import datetime

from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from ...utils.periods import ReportingPeriod
from ..forms import IssueFilterForm
from ..models import ActivityEvent, Computer


_ISSUE_LIMIT = 100


class IssuePanel:
    """Build the issues and logs shown below the computer list."""

    def __init__(self, request: HttpRequest) -> None:
        self.request = request

    def build_context(self, *, logs_only: bool = False) -> dict[str, object]:
        """Build filter, enforcement-failure, and diagnostic-log context."""
        request = self.request
        data = request.GET.copy()
        data.setdefault("issues-period", ReportingPeriod.DAYS_7)
        form = IssueFilterForm(data, prefix="issues")
        query = data.copy()

        for name in tuple(query):

            if name not in {"issues-computer", "issues-period", "log", "access", "connection", "config_delivery"}:
                del query[name]

        context: dict[str, object] = {
            "issue_filter": form,
            "issues_url": reverse("core:computers"),
            "issues_query": query,
            "issue_rows": (),
            "diagnostic_logs": (),
            "issue_count": 0,
            "log_count": 0,
            "issue_limit": _ISSUE_LIMIT,
            "logs_only": logs_only,
        }

        if not form.is_valid():
            return context

        computer = form.get_computer()
        since = form.get_since(timezone.now())
        logs = tuple(Computer.get_diagnostic_logs(computer, since).order_by("hostname", "pk"))
        selected = request.GET.get("log")
        active_log_id = next((item.pk for item in logs if f"{item.pk}" == selected), logs[0].pk if logs else None)
        context.update({"diagnostic_logs": logs, "log_count": len(logs), "active_log_id": active_log_id})

        if logs_only:
            return context

        failures = ActivityEvent.objects.get_enforcement_failures(
            computer=computer,
            since=since,
        )
        issue_count = failures.count()
        context.update(
            {
                "issue_rows": self.build_issue_rows(failures[:_ISSUE_LIMIT]),
                "issue_count": issue_count,
                "issues_truncated": issue_count > _ISSUE_LIMIT,
            }
        )
        return context

    @classmethod
    def build_issue_rows(cls, failures: Iterable[ActivityEvent]) -> tuple[dict[str, object], ...]:
        """Convert stored failures to rows in sanea's current timezone."""
        rows = []
        add_row = rows.append

        for failure in failures:
            account = failure.account
            computer = account.computer
            add_row(
                {
                    "account": account,
                    "computer": computer,
                    "timestamp": datetime.fromtimestamp(
                        failure.timestamp,
                        timezone.get_current_timezone(),
                    ),
                    "reason": cls.format_reason(failure.reason),
                    "meta": cls.format_meta(failure.meta),
                }
            )

        return tuple(rows)

    @staticmethod
    def format_reason(reason: str | None) -> str:
        """Format a protocol reason for display without hiding its meaning."""

        if not reason:
            unknown_reason = _("Unknown reason")
            return f"{unknown_reason}"

        return reason.replace("_", " ").capitalize()

    @staticmethod
    def format_meta(meta: dict[str, object]) -> str:
        """Format optional structured details without changing their content."""

        if not meta:
            return ""

        return json.dumps(meta, ensure_ascii=False, indent=2, sort_keys=True)

    def render_content(self) -> HttpResponse:
        """Render only the filtered issue panel."""
        return render(self.request, "sanea/issues/_content.html", self.build_context())

    def render_logs(self) -> HttpResponse:
        """Refresh log snapshots without querying or replacing the failure list."""
        return render(self.request, "sanea/issues/_logs.html", self.build_context(logs_only=True))
