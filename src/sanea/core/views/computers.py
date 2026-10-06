"""Registered computer views."""

from collections.abc import Callable, Mapping
from urllib.parse import urlencode

from django.core.paginator import Paginator
from django.db.models import Count, Q, QuerySet
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.utils.functional import Promise

from ..forms import CommandFilterForm, ComputerFilterForm, ComputerForm, SanexUpdateForm
from ..models import ClientCommand, CommandStatus, Computer, GlobalUpdate
from ..services.registration_window import registration_window
from .base import ManagedView
from ..models.client_command import CommandRepeatResult
from ..models.global_update import UpdateActivationResult


COMMAND_PAGE_SIZE = 100


class ComputersView(ManagedView):
    """List computers, register clients, and manage client commands."""

    def get_ajax_handlers(self) -> dict[str, Callable[..., HttpResponse]]:
        """Return computer, registration, update, and history handlers."""
        return {
            "computer-details-*": self.render_details,
            "computer-configure-*": self.render_editor,
            "computer-cancel-*": self.render_details,
            "computer-save": self.save_computer,
            "computer-close-*": self.close_details,
            "computer-commands-*": self.render_command_history,
            "computer-command-pending-*": self.render_command_history,
            "computer-command-failed-*": self.render_command_history,
            "registration-open": self.open_registration,
            "registration-refresh": self.render_registration,
            "update-save": self.queue_update,
            "update-cancel": self.cancel_update,
            "computer-live-refresh": self.render_live_refresh,
            "command-filter": self.render_command_history,
            "command-page-*": self.render_command_history,
            "command-repeat-*": self.repeat_command,
            "computer-filter": self.render_computer_list,
        }

    def dispatch(self, request: HttpRequest, **kwargs: object) -> HttpResponse:
        """Render the complete page and handle non-JavaScript actions."""
        update_context = self.build_update_context()
        computer = None
        computer_form = None
        request_data = request.POST

        if request.method == "POST":
            submit = request_data.get("__submit")

            if submit == "update":
                update_context = self.process_update(request)

            elif submit == "update_cancel":
                self.cancel_active_update()
                url = reverse("core:computers")
                return redirect(f"{url}#sanex-updates")

            elif submit == "command_repeat":
                self.repeat_requested_command(request)
                url = reverse("core:computers")
                return redirect(f"{url}#command-history")

            elif submit == "computer":
                computer, computer_form = self.build_computer_form(request)

                if computer_form.is_submitted and computer_form.is_valid():
                    saved = Computer.save_form(computer_form)
                    url = reverse("core:computers")
                    return redirect(f"{url}?computer={saved.pk}")

            else:
                registration_window.open()
                return redirect("core:computers")

        elif request.GET.get("computer"):
            computer = self.get_requested_computer(request)

            if request.GET.get("edit"):
                computer_form = self.build_unbound_computer_form(computer)

        context = {
            "page_title": _("Computers"),
            **self.build_computer_list_context(request),
            "computer": computer,
            "computer_form": computer_form,
            **self.build_registration_context(),
            **update_context,
            **self.build_command_history_context(request),
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
            "list_oob": list_oob,
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
        return render(request, "sanea/computers/_details.html", context)

    def close_details(self, request: HttpRequest, **kwargs: object) -> HttpResponse:
        """Close the computer detail panel."""
        return HttpResponse()

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

    def build_update_context(
        self,
        form: SanexUpdateForm | None = None,
        result: UpdateActivationResult | dict[str, int] | None=None,
    ) -> dict[str, object]:
        """Build the global sanex update form context."""
        return {
            "update_form": form or SanexUpdateForm(render_form_tag=False),
            "update_result": result,
            "active_update": GlobalUpdate.get_active(),
            "computers_url": reverse("core:computers"),
        }

    def build_computer_list_context(
        self,
        request: HttpRequest,
    ) -> dict[str, object]:
        """Validate overview filters and build the computer list context."""
        data = request.GET or {}
        form = ComputerFilterForm(data, render_form_tag=False)
        computers = self.get_computers()

        if form.is_valid():
            computers = self.get_computers(**form.get_filters())

        return {
            "computer_filter": form,
            "computers": computers,
            "computers_url": reverse("core:computers"),
        }

    def build_command_filter_query(self, data: Mapping[str, str]) -> str:
        """Preserve list and command filters across history pages."""
        field_names = (*ComputerFilterForm.base_fields, *CommandFilterForm.base_fields)
        return urlencode(
            [
                (field_name, value)
                for field_name in field_names
                if (value := data.get(field_name))
            ]
        )

    def build_command_history_context(
        self,
        request: HttpRequest,
        *,
        message: str | Promise | None=None,
    ) -> dict[str, object]:
        """Build filtered and paginated command history context."""
        request_data = request.POST if request.method == "POST" else request.GET
        data = request_data or {"command_status": ""}
        form = CommandFilterForm(data, render_form_tag=False)
        commands = ()

        if form.is_valid():
            commands = ClientCommand.get_recent(**form.get_filters())

        command_page = Paginator(commands, COMMAND_PAGE_SIZE).get_page(
            data.get("command_page")
        )
        return {
            "command_filter": form,
            "command_filter_query": self.build_command_filter_query(data),
            "command_page": command_page,
            "command_rows": command_page.object_list,
            "computers_url": reverse("core:computers"),
            "message": message,
        }

    def repeat_requested_command(self, request: HttpRequest) -> CommandRepeatResult:
        """Repeat the failed command named by the request."""
        command = get_object_or_404(
            ClientCommand,
            pk=request.POST.get("command"),
            status=CommandStatus.FAILED,
        )
        return command.repeat()

    def process_update(self, request: HttpRequest) -> dict[str, object]:
        """Validate a global update request and queue its command."""
        form = SanexUpdateForm(
            request=request,
            src="POST",
            submit_marker="update",
            render_form_tag=False,
        )
        result = None

        if form.is_submitted and form.is_valid():
            result = GlobalUpdate.activate(form.get_payload())
            form = SanexUpdateForm(render_form_tag=False)

        return self.build_update_context(form, result)

    def queue_update(self, request: HttpRequest, **kwargs: object) -> HttpResponse:
        """Queue a validated update and refresh the update fragment."""
        context = self.process_update(request)
        return render(request, "sanea/computers/_updates.html", context)

    def cancel_active_update(self) -> int:
        """Cancel the active global update, if one exists."""
        update = GlobalUpdate.get_active()

        if update is None:
            return 0

        return update.cancel()

    def cancel_update(self, request: HttpRequest, **kwargs: object) -> HttpResponse:
        """Cancel the active global update and refresh its fragment."""
        cancelled = self.cancel_active_update()
        context = self.build_update_context(result={"cancelled": cancelled})
        return render(request, "sanea/computers/_updates.html", context)

    def render_computer_list(
        self,
        request: HttpRequest,
        **kwargs: object,
    ) -> HttpResponse:
        """Render the filtered computer list fragment."""
        context = self.build_computer_list_context(request)
        return render(request, "sanea/computers/_list.html", context)

    def render_command_history(
        self,
        request: HttpRequest,
        **kwargs: object,
    ) -> HttpResponse:
        """Render filtered command history."""
        context = self.build_command_history_context(request)
        return render(request, "sanea/computers/_command_history.html", context)

    def repeat_command(self, request: HttpRequest, **kwargs: object) -> HttpResponse:
        """Repeat one failed command and refresh command history."""
        result = self.repeat_requested_command(request)

        if result.created:
            message = _("Command queued again.")

        else:
            message = _("An identical command is already pending.")

        context = self.build_command_history_context(request, message=message)
        return render(request, "sanea/computers/_command_history.html", context)

    def render_live_refresh(self, request: HttpRequest, **kwargs: object) -> HttpResponse:
        """Render live-refresh fragments for computers and commands."""
        context = {
            **self.build_computer_list_context(request),
            **self.build_command_history_context(request),
        }
        return render(request, "sanea/computers/_live_refresh.html", context)


computers = ComputersView().as_view()
