"""Reported client issues and diagnostic logs."""

import json
from collections.abc import Callable, Iterable
from datetime import datetime
from zoneinfo import ZoneInfo

from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from ...utils.periods import ReportingPeriod
from ..forms import IssueFilterForm
from ..models import ActivityEvent, Computer
from .base import ManagedView


_ISSUE_LIMIT = 100


class _IssuePresenter:
    """Build one filtered issue-list presentation."""

    def __init__(self, request: HttpRequest) -> None:
        self.request = request

    def build_context(self) -> dict[str, object]:
        """Build filter, enforcement-failure, and diagnostic-log context."""
        request = self.request
        data = request.GET or {"period": ReportingPeriod.DAYS_7}
        form = IssueFilterForm(data)
        context: dict[str, object] = {
            "issue_filter": form,
            "issues_url": reverse("core:issues"),
            "issue_rows": (),
            "diagnostic_logs": (),
            "issue_count": 0,
            "log_count": 0,
            "issue_limit": _ISSUE_LIMIT,
        }

        if not form.is_valid():
            return context

        computer = form.get_computer()
        since = form.get_since(timezone.now())
        failures = ActivityEvent.objects.get_enforcement_failures(
            computer=computer,
            since=since,
        )
        logs = Computer.get_diagnostic_logs(computer, since)
        issue_count = failures.count()
        log_count = logs.count()
        context.update(
            {
                "issue_rows": self.build_issue_rows(failures[:_ISSUE_LIMIT]),
                "diagnostic_logs": logs,
                "issue_count": issue_count,
                "log_count": log_count,
                "issues_truncated": issue_count > _ISSUE_LIMIT,
            }
        )
        return context

    @classmethod
    def build_issue_rows(cls, failures: Iterable[ActivityEvent]) -> tuple[dict[str, object], ...]:
        """Convert stored failures to rows localized to each computer."""
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
                        ZoneInfo(computer.timezone),
                    ),
                    "reason": cls.format_reason(failure.reason),
                    "rule_ident": failure.rule_ident,
                    "wnd_ident": failure.wnd_ident,
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


class IssuesView(ManagedView):
    """Display enforcement failures and the latest diagnostic logs."""

    def get_ajax_handlers(self) -> dict[str, Callable[..., HttpResponse]]:
        """Return the independently refreshable issue handler."""
        return {"issue-filter": self.render_issues}

    def dispatch(self, request: HttpRequest, **kwargs: object) -> HttpResponse:
        """Render the complete issues page."""
        context = {
            "page_title": _("Issues"),
            **_IssuePresenter(request).build_context(),
        }
        return render(request, "sanea/issues/index.html", context)

    def render_issues(self, request: HttpRequest, **kwargs: object) -> HttpResponse:
        """Render the independently refreshable issue fragment."""
        context = _IssuePresenter(request).build_context()
        return render(request, "sanea/issues/_content.html", context)


issues = IssuesView().as_view()
