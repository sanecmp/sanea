"""Limits template management views."""

from collections.abc import Callable

from django.db.models import Count, Prefetch, QuerySet
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from ..forms import LimitsTemplateForm, TemplatePropagationForm
from ..models import Account, LimitsTemplate
from .editor import ModelEditorView
from .ignored_processes import IgnoredProcessesEditor


class LimitsView(ModelEditorView[None, LimitsTemplate, LimitsTemplateForm]):
    """List and edit reusable limits templates."""

    page_title = _("Limits")
    section = "limits"
    page_template = "sanea/limits/index.html"
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
    process_editor = IgnoredProcessesEditor()

    def get_page_context(
        self,
        request: HttpRequest,
        scope: None,
        selected: LimitsTemplate | None,
        form: LimitsTemplateForm | None,
    ) -> dict[str, object]:
        """Add global process exclusions below the template list."""
        return {
            **self.process_editor.get_list_context(scope),
            "ignored_process_editor": self.process_editor.build_editor_context(scope, None, None),
            "ignored_processes_url": reverse("core:limits"),
        }

    def dispatch(self, request: HttpRequest, **kwargs: object) -> HttpResponse:
        """Support both editors and template distribution without JavaScript."""

        if request.GET.get("exclusion") or request.POST.get("exclusion") or request.POST.get("__submit") == "exclusion":
            return self.handle_process_editor(request)

        if request.method == "POST" and request.POST.get("apply_template"):
            return self.apply_template(request, partial=False)

        if request.GET.get("apply"):
            return self.render_application(request, partial=False)

        return super().dispatch(request, **kwargs)

    def handle_process_editor(self, request: HttpRequest) -> HttpResponse:
        """Keep ordinary process forms and their errors on the limits page."""
        editor = self.process_editor

        if request.method == "POST" and request.POST.get("delete"):
            editor.disable_requested_exclusion(request)
            return redirect(editor.get_success_url(None, None))

        exclusion, form = editor.build_form(request, None)

        if request.method == "POST" and form.is_submitted and form.is_valid():
            editor.save_form(form, exclusion, None)
            return redirect(editor.get_success_url(exclusion, None))

        context = self.build_page_context(request, None, None, None)
        context["ignored_process_editor"] = editor.build_editor_context(None, exclusion, form)
        return render(request, self.page_template, context)

    def get_extra_ajax_handlers(self) -> dict[str, Callable[..., HttpResponse]]:
        """Keep template application beside the template settings."""
        return {
            **self.process_editor.get_ajax_handlers(),
            "limits-apply-*": self.render_application,
            "limits-apply-save": self.apply_template,
            "limits-apply-cancel": self.close_editor,
        }

    def render_application(
        self, request: HttpRequest, *, partial: bool = True, **kwargs: object,
    ) -> HttpResponse:
        """Show the eligible accounts without changing their limits."""
        template = self.get_requested_template(request)

        if template is None:
            return HttpResponse(status=404)

        form = self.build_application_form(request, template)
        return self.render_application_response(request, template, form, partial=partial)

    def apply_template(
        self, request: HttpRequest, *, partial: bool = True, **kwargs: object,
    ) -> HttpResponse:
        """Apply the template only after explicit account selection."""
        template = self.get_requested_template(request)

        if template is None:
            return HttpResponse(status=404)

        form = self.build_application_form(request, template)

        if not form.is_submitted or not form.is_valid():
            return self.render_application_response(request, template, form, partial=partial)

        count = template.apply_to_accounts(form.cleaned_data["accounts"])

        if not partial:
            return redirect("core:limits")

        return self.render_saved_response(request, None, f"{_("Accounts updated:")} {count}.")

    def build_application_form(self, request: HttpRequest, template: LimitsTemplate) -> TemplatePropagationForm:
        """Build explicit account choices for one template."""
        return TemplatePropagationForm(
            request=request, src="POST", prefix="propagation", template=template, render_form_tag=False,
        )

    def render_application_response(
        self, request: HttpRequest, template: LimitsTemplate, form: TemplatePropagationForm, *, partial: bool,
    ) -> HttpResponse:
        """Render application errors in a fragment or an ordinary page."""
        context = self.build_editor_context(None, template, form)
        context["propagation_form"] = form
        context["editor"].update(
            {
                "template": "sanea/limits/_apply.html",
                "save_id": "limits-apply-save",
                "cancel_id": "limits-apply-cancel",
            }
        )

        if partial:
            return render(request, "sanea/limits/_apply.html", context)

        page_context = self.build_page_context(request, None, template, None)
        page_context.update(context)
        return render(request, self.page_template, page_context)

    def get_requested_template(self, request: HttpRequest) -> LimitsTemplate | None:
        """Resolve an optional template reference."""
        reference = request.POST.get("limits", request.GET.get("limits", ""))

        if not reference or reference == "new":
            return None

        return get_object_or_404(LimitsTemplate, pk=reference)

    def get_scope(self, **kwargs: object) -> None:
        """Return the empty top-level scope."""

    def build_form(
        self,
        request: HttpRequest,
        scope: None,
    ) -> tuple[LimitsTemplate | None, LimitsTemplateForm]:
        """Build a form for a selected or new template."""
        selected = self.get_requested_template(request)
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
        """Return each template's current rule counts, people and accounts."""
        limits_sets: QuerySet[LimitsTemplate] = LimitsTemplate.objects.select_related(
            "current_limits"
        ).annotate(
            range_count=Count("current_limits__ranges", distinct=True),
            rule_count=Count("current_limits__session_rules", distinct=True),
        ).prefetch_related(
            "people",
            Prefetch(
                "current_limits__accounts",
                queryset=Account.objects.select_related("computer").order_by("computer__name", "login", "pk"),
                to_attr="latest_accounts",
            ),
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
