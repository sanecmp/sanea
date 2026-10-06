"""Limits template management views."""

from django.db.models import Count, QuerySet
from django.http import HttpRequest
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from ..forms import LimitsTemplateForm
from ..models import LimitsTemplate
from .editor import ModelEditorView


class LimitsView(ModelEditorView[None, LimitsTemplate, LimitsTemplateForm]):
    """List and edit reusable limits templates."""

    page_title = _("Limits")
    section = "limits"
    editor_id = "limits-editor"
    editor_template = "sanea/limits/_editor.html"
    reference_name = "limits"
    selected_context_name = "limits"
    form_context_name = "limits_form"
    url_context_name = "limits_url"
    saved_message = _("Limits template saved.")
    add_trigger = "limits-add"
    edit_trigger = "limits-edit-*"
    save_trigger = "limits-save"
    cancel_trigger = "limits-cancel"

    def get_scope(self, **kwargs: object) -> None:
        """Return the empty top-level scope."""

    def build_form(
        self,
        request: HttpRequest,
        scope: None,
    ) -> tuple[LimitsTemplate | None, LimitsTemplateForm]:
        """Build a form for a selected or new template."""
        reference = request.POST.get("limits", request.GET.get("limits", ""))
        selected = None

        if reference and reference != "new":
            selected = get_object_or_404(LimitsTemplate, pk=reference)

        form = LimitsTemplateForm(
            request=request,
            src="POST",
            prefix="limits",
            instance=selected,
            render_form_tag=False,
        )
        return selected, form

    def save_form(
        self,
        form: LimitsTemplateForm,
        selected: LimitsTemplate | None,
        scope: None,
    ) -> LimitsTemplate:
        """Persist a limits template through its model API."""
        return LimitsTemplate.save_form(form)

    def get_scope_context(self, scope: None) -> dict[str, object]:
        """Return the empty top-level context."""
        return {}

    def get_list_context(self, scope: None) -> dict[str, object]:
        """Return annotated limits templates for the list fragment."""
        limits_sets: QuerySet[LimitsTemplate] = LimitsTemplate.objects.select_related(
            "current_limits"
        ).annotate(
            person_count=Count("people", distinct=True),
            account_count=Count("current_limits__accounts", distinct=True),
            range_count=Count("current_limits__ranges", distinct=True),
            rule_count=Count("current_limits__session_rules", distinct=True),
        )
        return {"limits_sets": limits_sets}

    def get_success_url(
        self,
        selected: LimitsTemplate | None,
        scope: None,
    ) -> str:
        """Return the limits index URL."""
        return reverse("core:limits")


limits = LimitsView().as_view()
