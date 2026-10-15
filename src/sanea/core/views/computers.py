"""Registered computer views."""

from collections.abc import Callable

from django.db.models import Count, Q, QuerySet
from django.http import HttpRequest, HttpResponse, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.functional import Promise
from django.utils.translation import gettext_lazy as _

from ..forms import ComputerDetailsForm, ComputerFilterForm, ComputerForm
from ..models import CommandStatus, Computer
from ..services.registration_window import registration_window
from .base import ManagedView
from .issues import IssuePanel


class ComputersView(ManagedView):
    """List registered computers and inspect or edit them in a dialog."""

    def get_ajax_handlers(self) -> dict[str, Callable[..., HttpResponse]]:
        """Return computer dialog, registration and list handlers."""
        return {
            "computer-details-*": self.render_details,
            "computer-configure-*": self.render_editor,
            "computer-cancel-*": self.render_details,
            "computer-save": self.save_computer,
            "registration-open": self.open_registration,
            "registration-refresh": self.render_registration,
            "computer-live-refresh": self.render_live_refresh,
            "computer-filter": self.render_computer_list,
            "issue-filter": self.render_issues,
            "diagnostic-refresh": self.render_logs,
        }

    def dispatch(self, request: HttpRequest, **kwargs: object) -> HttpResponse:
        """Render the overview and handle forms without JavaScript."""
        details_context = {}

        if request.method == "POST":
            submit = request.POST.get("__submit")

            if submit == "registration":
                registration_window.open()
                return redirect(f"{reverse('core:computers')}?registration=1#registration-window")

            if submit != "computer":
                return HttpResponseBadRequest()

            computer, form = self.build_computer_form(request)

            if form.is_submitted and form.is_valid():
                saved = Computer.save_form(form)
                return redirect(f"{reverse('core:computers')}?computer={saved.pk}")

            details_context = self.build_editor_context(computer, form)

        elif request.GET.get("computer"):
            computer = self.get_requested_computer(request)
            details_context = (
                self.build_editor_context(computer, self.build_unbound_computer_form(computer))
                if request.GET.get("edit") else self.build_details_context(computer)
            )

        context = {
            "page_title": _("Computers"),
            **self.build_computer_list_context(request),
            **self.build_registration_context(),
            **IssuePanel(request).build_context(),
            **details_context,
            "registration_expanded": bool(request.GET.get("registration")) or bool(registration_window.get_snapshot()),
        }
        return render(request, "sanea/computers/index.html", context)

    def get_computers(self, **filters: str | None) -> QuerySet[Computer]:
        """Return computers with all overview counters and configurations."""
        return (
            Computer.filter_for_overview(**filters)
            .select_related("current_config", "applied_config")
            .annotate(
                account_count=Count("accounts", distinct=True),
                collecting_count=Count(
                    "accounts",
                    filter=Q(accounts__collect=True),
                    distinct=True,
                ),
                pending_command_count=Count(
                    "commands",
                    filter=Q(commands__status__isnull=True),
                    distinct=True,
                ),
                failed_command_count=Count(
                    "commands",
                    filter=Q(commands__status=CommandStatus.FAILED),
                    distinct=True,
                ),
            )
        )

    def get_requested_computer(self, request: HttpRequest) -> Computer:
        """Resolve a computer reference from either request method."""
        reference = request.POST.get(
            "computer",
            request.GET.get("computer", ""),
        )
        return get_object_or_404(self.get_computers(), pk=reference)

    def build_details_context(
        self,
        computer: Computer,
        *,
        message: str | Promise | None=None,
        list_oob: bool = False,
    ) -> dict[str, object]:
        """Build the shared computer-detail fragment context."""
        return {
            "computer": computer,
            "computers_url": reverse("core:computers"),
            "message": message,
            "table_oob": list_oob,
            "computer_form": ComputerDetailsForm(instance=computer, readonly_fields="__all__", render_form_tag=False),
            "read_only": True,
        }

    def render_details(self, request: HttpRequest, **kwargs: object) -> HttpResponse:
        """Render one computer's details."""
        computer = self.get_requested_computer(request)
        context = self.build_details_context(computer)
        return render(request, "sanea/computers/_details.html", context)

    def build_computer_form(
        self,
        request: HttpRequest,
    ) -> tuple[Computer, ComputerForm]:
        """Build a submitted settings form for the requested computer."""
        computer = self.get_requested_computer(request)
        form = ComputerForm(
            request=request,
            src="POST",
            prefix="computer",
            instance=computer,
            render_form_tag=False,
        )
        return computer, form

    def build_unbound_computer_form(self, computer: Computer) -> ComputerForm:
        """Build an unbound settings form for one computer."""
        return ComputerForm(
            prefix="computer",
            instance=computer,
            render_form_tag=False,
        )

    def build_editor_context(
        self,
        computer: Computer,
        form: ComputerForm,
    ) -> dict[str, object]:
        """Build the computer editor fragment context."""
        return {
            "computer": computer,
            "computer_form": form,
            "read_only": False,
            "computers_url": reverse("core:computers"),
        }

    def render_editor(self, request: HttpRequest, **kwargs: object) -> HttpResponse:
        """Render settings for the requested computer."""
        computer = self.get_requested_computer(request)
        form = self.build_unbound_computer_form(computer)
        context = self.build_editor_context(computer, form)
        return render(request, "sanea/computers/_editor.html", context)

    def save_computer(self, request: HttpRequest, **kwargs: object) -> HttpResponse:
        """Validate computer settings and refresh its detail fragment."""
        computer, form = self.build_computer_form(request)

        if not form.is_submitted or not form.is_valid():
            context = self.build_editor_context(computer, form)
            return render(request, "sanea/computers/_editor.html", context)

        saved = Computer.save_form(form)
        computer = self.get_computers().get(pk=saved.pk)
        context = self.build_details_context(
            computer,
            message=_("Computer settings saved."),
            list_oob=True,
        )
        context.update(self.build_computer_list_context(request))
        return render(request, "sanea/computers/_details.html", context)

    def build_registration_context(self) -> dict[str, object]:
        """Build the current registration-window context."""
        return {
            "registration": registration_window.get_snapshot(),
            "computers_url": reverse("core:computers"),
        }

    def render_registration(self, request: HttpRequest, **kwargs: object) -> HttpResponse:
        """Render the registration-window fragment."""
        context = self.build_registration_context()
        return render(request, "sanea/computers/_registration.html", context)

    def open_registration(self, request: HttpRequest, **kwargs: object) -> HttpResponse:
        """Open registration and return its updated fragment."""
        registration_window.open()
        return self.render_registration(request)

    def build_computer_list_context(
        self,
        request: HttpRequest,
    ) -> dict[str, object]:
        """Validate overview filters and build the computer list context."""
        data = (request.POST if request.method == "POST" else request.GET) or {}
        form = ComputerFilterForm(data, render_form_tag=False)
        computers = self.get_computers()

        if form.is_valid():
            computers = self.get_computers(**form.get_filters())

        return {
            "computer_filter": form,
            "computers": computers,
            "computers_url": reverse("core:computers"),
        }

    def render_computer_list(
        self,
        request: HttpRequest,
        **kwargs: object,
    ) -> HttpResponse:
        """Render the filtered computer list fragment."""
        context = self.build_computer_list_context(request)
        return render(request, "sanea/computers/_list.html", context)

    def render_live_refresh(self, request: HttpRequest, **kwargs: object) -> HttpResponse:
        """Refresh the overview without replacing filters or the dialog."""
        context = self.build_computer_list_context(request)
        return render(request, "sanea/computers/_table.html", context)

    def render_issues(self, request: HttpRequest, **kwargs: object) -> HttpResponse:
        """Filter issues without replacing the computer list."""
        return IssuePanel(request).render_content()

    def render_logs(self, request: HttpRequest, **kwargs: object) -> HttpResponse:
        """Refresh diagnostic logs only when requested."""
        return IssuePanel(request).render_logs()


computers = ComputersView().as_view()
