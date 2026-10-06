"""Weekly schedule range management views."""

from django.http import HttpRequest
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from ...utils.schedule import WEEKDAY_CHOICES, format_clock
from ..forms import RangeForm
from ..models import Limits, Range
from .editor import ModelEditorView


class RangesView(ModelEditorView[Limits, Range, RangeForm]):
    """List and edit weekly ranges belonging to one limits set."""

    page_title = _("Schedule ranges")
    section = "ranges"
    editor_id = "range-editor"
    editor_template = "sanea/ranges/_editor.html"
    reference_name = "range"
    selected_context_name = "range"
    form_context_name = "range_form"
    url_context_name = "ranges_url"
    saved_message = _("Schedule range saved.")
    add_trigger = "range-add"
    edit_trigger = "range-edit-*"
    save_trigger = "range-save"
    cancel_trigger = "range-cancel"

    def get_scope(self, **kwargs: object) -> Limits:
        """Resolve the limits set from the nested URL."""
        return get_object_or_404(Limits, pk=kwargs["limits_pk"])

    def build_form(
        self,
        request: HttpRequest,
        scope: Limits,
    ) -> tuple[Range | None, RangeForm]:
        """Build a form for a selected or new schedule range."""
        reference = request.POST.get("range", request.GET.get("range", ""))
        selected = None

        if reference and reference != "new":
            selected = get_object_or_404(Range, limits=scope, pk=reference)

        form = RangeForm(
            request=request,
            src="POST",
            prefix="range",
            instance=selected,
            limits=scope,
            render_form_tag=False,
        )
        return selected, form

    def save_form(
        self,
        form: RangeForm,
        selected: Range | None,
        scope: Limits,
    ) -> Range:
        """Persist a schedule range through its model API."""
        return Range.save_form(form, scope)

    def get_scope_context(self, scope: Limits) -> dict[str, object]:
        """Expose the parent limits set to all templates."""
        return {"limits": scope}

    def get_list_context(self, scope: Limits) -> dict[str, object]:
        """Return ranges with labels prepared for the list fragment."""
        weekday_labels = dict(WEEKDAY_CHOICES)
        ranges = list(Range.objects.filter(limits=scope).select_related("session_rule"))

        for range_ in ranges:
            range_.weekday_label = weekday_labels[range_.weekday]
            range_.since_label = format_clock(range_.since)
            range_.till_label = format_clock(range_.till)

        return {"ranges": ranges}

    def get_page_context(
        self,
        request: HttpRequest,
        scope: Limits,
        selected: Range | None,
        form: RangeForm | None,
    ) -> dict[str, object]:
        """Expose whether a range can reference any session rule."""
        return {"has_session_rules": scope.session_rules.exists()}

    def get_success_url(
        self,
        selected: Range | None,
        scope: Limits,
    ) -> str:
        """Return the canonical URL for the saved range's limits set."""
        limits_id = selected.limits_id if selected is not None else scope.pk
        return reverse("core:ranges", args=(limits_id,))

    def get_ajax_redirect_url(
        self,
        saved: Range,
        scope: Limits,
    ) -> str | None:
        """Redirect when the range was moved to another limits set."""

        if saved.limits_id == scope.pk:
            return None

        return self.get_success_url(saved, scope)


ranges = RangesView().as_view()
