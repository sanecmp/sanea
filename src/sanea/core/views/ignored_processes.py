"""Management of process names excluded from activity accounting."""

from collections.abc import Callable

from django.db.models import QuerySet
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.utils.functional import Promise

from ..forms import PrcExclusionForm
from ..models import PrcExclusion
from .editor import ModelEditorView


class IgnoredProcessesEditor(ModelEditorView[None, PrcExclusion, PrcExclusionForm]):
    """Manage process exclusions in the limits page's dialog."""

    page_title = _("Ignored processes")
    section = "ignored_processes"
    message_id = "ignored-processes-message"
    editor_id = "ignored-process-editor"
    editor_template = "sanea/ignored_processes/_editor.html"
    reference_name = "exclusion"
    selected_context_name = "exclusion"
    form_context_name = "exclusion_form"
    url_context_name = "ignored_processes_url"
    saved_message = _("Ignored process saved.")
    add_trigger = "ignored-process-add"
    edit_trigger = "ignored-process-edit-*"
    save_trigger = "ignored-process-save"
    cancel_trigger = "ignored-process-cancel"

    def get_extra_ajax_handlers(self) -> dict[str, Callable[..., HttpResponse]]:
        """Add the exclusion removal handler."""
        return {
            "ignored-process-delete-*": self.disable_exclusion,
        }

    def disable_exclusion(self, request: HttpRequest, **kwargs: object) -> HttpResponse:
        """Disable one exclusion and replace the list fragment."""
        self.disable_requested_exclusion(request)
        return self.render_action_saved(request, _("Ignored process removed."))

    def disable_requested_exclusion(self, request: HttpRequest) -> None:
        """Resolve and disable the exclusion named by the request."""
        exclusion = self.get_requested_exclusion(request)
        exclusion.delete_and_materialize()

    def render_action_saved(self, request: HttpRequest, message: str | Promise) -> HttpResponse:
        """Render one exclusion action through the common saved fragment."""
        return self.render_saved_response(request, None, message)

    def get_scope(self, **kwargs: object) -> None:
        """Return the empty top-level scope."""

    def build_form(
        self,
        request: HttpRequest,
        scope: None,
    ) -> tuple[PrcExclusion | None, PrcExclusionForm]:
        """Build the same form for adding and editing an exclusion."""
        reference = request.POST.get("exclusion", request.GET.get("exclusion", "new"))
        exclusion = None if reference == "new" else self.get_requested_exclusion(request)
        form = PrcExclusionForm(
            request=request,
            src="POST",
            prefix="exclusion",
            instance=exclusion,
            render_form_tag=False,
        )
        return exclusion, form

    def save_form(
        self,
        form: PrcExclusionForm,
        selected: PrcExclusion | None,
        scope: None,
    ) -> PrcExclusion:
        """Save and distribute one validated process exclusion."""
        return form.instance.save_and_materialize()

    def get_scope_context(self, scope: None) -> dict[str, object]:
        """Return the empty top-level context."""
        return {}

    def get_list_context(self, scope: None) -> dict[str, object]:
        """Return only names currently excluded from reports."""
        exclusions: QuerySet[PrcExclusion] = PrcExclusion.objects.filter(apply=True)
        return {"ignored_processes": exclusions}

    def get_success_url(
        self,
        selected: PrcExclusion | None,
        scope: None,
    ) -> str:
        """Return to the process list below the templates."""
        return f"{reverse('core:limits')}#ignored-processes"

    def get_requested_exclusion(self, request: HttpRequest) -> PrcExclusion:
        """Resolve the exclusion named by a state-change request."""
        return get_object_or_404(
            PrcExclusion.objects.filter(apply=True),
            pk=request.POST.get("exclusion", request.GET.get("exclusion", "")),
        )
