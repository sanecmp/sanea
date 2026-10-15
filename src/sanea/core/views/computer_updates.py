"""Global sanex update settings."""

from collections.abc import Callable

from django.http import HttpRequest, HttpResponse, HttpResponseBadRequest
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from ..forms import SanexUpdateForm
from ..models import GlobalUpdate
from ..models.global_update import UpdateActivationResult
from .base import ManagedView


class ComputerUpdatesView(ManagedView):
    """Manage global client updates on a dedicated page."""

    def get_ajax_handlers(self) -> dict[str, Callable[..., HttpResponse]]:
        """Return update form handlers."""
        return {"update-save": self.queue_update, "update-cancel": self.cancel_update}

    def dispatch(self, request: HttpRequest, **kwargs: object) -> HttpResponse:
        """Render update settings and support ordinary form submissions."""
        context = self.build_update_context()

        if request.method == "POST":
            submit = request.POST.get("__submit")

            if submit == "update":
                context = self.process_update(request)

            elif submit == "update_cancel":
                self.cancel_active_update()
                return redirect("core:computer_updates")

            else:
                return HttpResponseBadRequest()

        context["page_title"] = _("Updates")
        return render(request, "sanea/computers/updates.html", context)

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
            "updates_url": reverse("core:computer_updates"),
        }

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


computer_updates = ComputerUpdatesView().as_view()
