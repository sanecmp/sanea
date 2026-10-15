"""Command history for registered computers."""

from collections.abc import Callable, Mapping
from urllib.parse import urlencode

from django.core.paginator import Paginator
from django.http import HttpRequest, HttpResponse, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.functional import Promise
from django.utils.translation import gettext_lazy as _

from ..forms import CommandFilterForm
from ..models import ClientCommand, CommandStatus
from ..models.client_command import CommandRepeatResult
from .base import ManagedView


COMMAND_PAGE_SIZE = 100


class ComputerCommandsView(ManagedView):
    """Filter, inspect and repeat commands on a dedicated page."""

    def get_ajax_handlers(self) -> dict[str, Callable[..., HttpResponse]]:
        """Return explicit history and background refresh handlers."""
        return {
            "command-filter": self.render_command_history,
            "command-page-*": self.render_command_history,
            "command-repeat-*": self.repeat_command,
            "command-live-refresh": self.render_live_refresh,
        }

    def dispatch(self, request: HttpRequest, **kwargs: object) -> HttpResponse:
        """Render history and handle ordinary repeat submissions."""

        if request.method == "POST":

            if request.POST.get("__submit") != "command_repeat":
                return HttpResponseBadRequest()

            self.repeat_requested_command(request)
            query = self.build_command_filter_query(request.POST)

            if page := request.POST.get("command_page"):
                page_query = urlencode({"command_page": page})
                query = f"{query}&{page_query}" if query else page_query

            url = reverse("core:computer_commands")
            return redirect(f"{url}?{query}" if query else url)

        context = {"page_title": _("Command history"), **self.build_command_history_context(request)}
        return render(request, "sanea/computers/commands.html", context)

    def build_command_filter_query(self, data: Mapping[str, str]) -> str:
        """Preserve list and command filters across history pages."""
        field_names = CommandFilterForm.base_fields
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
            "commands_url": reverse("core:computer_commands"),
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
        """Refresh results without replacing the filter controls."""
        context = self.build_command_history_context(request)
        return render(request, "sanea/computers/_command_table.html", context)


computer_commands = ComputerCommandsView().as_view()
