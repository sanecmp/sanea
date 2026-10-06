"""Management of process names excluded from activity accounting."""

from collections.abc import Callable

from django.db.models import QuerySet
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.utils.functional import Promise

from ..forms import PrcExclusionForm
from ..models import PrcExclusion
from .editor import ModelEditorView


class IgnoredProcessesView(ModelEditorView[None, PrcExclusion, PrcExclusionForm]):
    """List and manage global exact process-name exclusions."""

    page_title = _("Ignored processes")
    section = "ignored_processes"
    editor_id = "ignored-process-editor"
    editor_template = "sanea/ignored_processes/_editor.html"
    reference_name = "exclusion"
    selected_context_name = "exclusion"
    form_context_name = "exclusion_form"
    url_context_name = "ignored_processes_url"
    saved_message = _("Ignored process added.")
    add_trigger = "ignored-process-add"
    save_trigger = "ignored-process-save"
    cancel_trigger = "ignored-process-cancel"

    def dispatch(self, request: HttpRequest, **kwargs: object) -> HttpResponse:
        """Handle non-JavaScript exclusion state changes and creation."""

        if request.method == "POST" and request.POST.get("delete"):
            self.disable_requested_exclusion(request)
            return redirect("core:ignored_processes")

        if request.method == "POST" and request.POST.get("restore"):
            self.restore_requested_exclusion(request)
            return redirect("core:ignored_processes")

        return super().dispatch(request, **kwargs)

    def get_extra_ajax_handlers(self) -> dict[str, Callable[..., HttpResponse]]:
        """Add exclusion disable and restore handlers."""
        return {
            "ignored-process-delete-*": self.disable_exclusion,
            "ignored-process-restore-*": self.restore_exclusion,
        }

    def disable_exclusion(self, request: HttpRequest, **kwargs: object) -> HttpResponse:
        """Disable one exclusion and replace the list fragment."""
        self.disable_requested_exclusion(request)
        return self.render_action_saved(request, _("Ignored process removed."))

    def restore_exclusion(self, request: HttpRequest, **kwargs: object) -> HttpResponse:
        """Restore one exclusion and replace the list fragment."""
        self.restore_requested_exclusion(request)
        return self.render_action_saved(request, _("Ignored process restored."))

    def disable_requested_exclusion(self, request: HttpRequest) -> None:
        """Resolve and disable the exclusion named by the request."""
        exclusion = self.get_requested_exclusion(request)
        exclusion.delete_and_materialize()

    def restore_requested_exclusion(self, request: HttpRequest) -> None:
        """Resolve and restore the exclusion named by the request."""
        exclusion = self.get_requested_exclusion(request)
        exclusion.restore_and_materialize()

    def render_action_saved(self, request: HttpRequest, message: str | Promise) -> HttpResponse:
        """Render one exclusion action through the common saved fragment."""
        return self.render_saved_response(request, None, message)

    def get_scope(self, **kwargs: object) -> None:
        """Return the empty top-level scope."""

    def build_form(
        self,
        request: HttpRequest,
        scope: None,
    ) -> tuple[None, PrcExclusionForm]:
        """Build the new-exclusion form."""
        form = PrcExclusionForm(
            request=request,
            src="POST",
            prefix="exclusion",
            render_form_tag=False,
        )
        return None, form

    def save_form(
        self,
        form: PrcExclusionForm,
        selected: PrcExclusion | None,
        scope: None,
    ) -> PrcExclusion:
        """Create and distribute one validated process exclusion."""
        return PrcExclusion.create_and_materialize(form.cleaned_data["prc_name"])

    def get_scope_context(self, scope: None) -> dict[str, object]:
        """Return the empty top-level context."""
        return {}

    def get_list_context(self, scope: None) -> dict[str, object]:
        """Return every active and disabled process exclusion."""
        exclusions: QuerySet[PrcExclusion] = PrcExclusion.objects.all()
        return {"ignored_processes": exclusions}

    def get_success_url(
        self,
        selected: PrcExclusion | None,
        scope: None,
    ) -> str:
        """Return the ignored-process settings URL."""
        return reverse("core:ignored_processes")

    def get_requested_exclusion(self, request: HttpRequest) -> PrcExclusion:
        """Resolve the exclusion named by a state-change request."""
        return get_object_or_404(
            PrcExclusion,
            pk=request.POST.get("exclusion"),
        )


ignored_processes = IgnoredProcessesView().as_view()
