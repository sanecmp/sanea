"""Parent dashboard view."""

from collections.abc import Callable

from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from ..models import Account, ClientCommand, Computer, Person
from .base import ManagedView


class _DashboardPresenter:
    """Build domain totals and operational status for the dashboard."""

    def build_context(self) -> dict[str, object]:
        """Build the complete page context."""
        return {
            "page_title": _("Dashboard"),
            "summary_cards": self.build_domain_cards(),
            **self.build_system_status_context(),
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


class DashboardView(ManagedView):
    """Render registered-domain totals and filterable operational summaries."""

    def get_ajax_handlers(self) -> dict[str, Callable[..., HttpResponse]]:
        """Return independently refreshable dashboard handlers."""
        return {
            "system-status": self.render_system_status,
        }

    def dispatch(self, request: HttpRequest, **kwargs: object) -> HttpResponse:
        """Render the complete dashboard."""
        context = _DashboardPresenter().build_context()
        return render(request, "sanea/dashboard.html", context)

    def render_system_status(
        self,
        request: HttpRequest,
        **kwargs: object,
    ) -> HttpResponse:
        """Render the independently refreshable operational summary."""
        context = _DashboardPresenter.build_system_status_context()
        return render(request, "sanea/dashboard/_system_status.html", context)


dashboard = DashboardView().as_view()
