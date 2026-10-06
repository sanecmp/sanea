"""Session rule management views."""

from django.db.models import Count, QuerySet
from django.http import HttpRequest
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from ..forms import SessionRuleForm
from ..models import Limits, SessionRule
from .editor import ModelEditorView


class SessionRulesView(ModelEditorView[Limits, SessionRule, SessionRuleForm]):
    """List and edit session rules belonging to one limits set."""

    page_title = _("Session rules")
    section = "session_rules"
    editor_id = "session-rule-editor"
    editor_template = "sanea/session_rules/_editor.html"
    reference_name = "rule"
    selected_context_name = "rule"
    form_context_name = "rule_form"
    url_context_name = "session_rules_url"
    saved_message = _("Session rule saved.")
    add_trigger = "session-rule-add"
    edit_trigger = "session-rule-edit-*"
    save_trigger = "session-rule-save"
    cancel_trigger = "session-rule-cancel"

    def get_scope(self, **kwargs: object) -> Limits:
        """Resolve the limits set from the nested URL."""
        return get_object_or_404(Limits, pk=kwargs["limits_pk"])

    def build_form(
        self,
        request: HttpRequest,
        scope: Limits,
    ) -> tuple[SessionRule | None, SessionRuleForm]:
        """Build a form for a selected or new session rule."""
        reference = request.POST.get("rule", request.GET.get("rule", ""))
        selected = None

        if reference and reference != "new":
            selected = get_object_or_404(SessionRule, limits=scope, pk=reference)

        form = SessionRuleForm(
            request=request,
            src="POST",
            prefix="rule",
            instance=selected,
            render_form_tag=False,
        )
        return selected, form

    def save_form(
        self,
        form: SessionRuleForm,
        selected: SessionRule | None,
        scope: Limits,
    ) -> SessionRule:
        """Persist a session rule through its model API."""
        return SessionRule.save_form(form, scope)

    def get_scope_context(self, scope: Limits) -> dict[str, object]:
        """Expose the parent limits set to all templates."""
        return {"limits": scope}

    def get_list_context(self, scope: Limits) -> dict[str, object]:
        """Return annotated rules for the list fragment."""
        rules: QuerySet[SessionRule] = SessionRule.objects.filter(
            limits=scope
        ).annotate(app_rule_count=Count("app_rules"))
        return {"rules": rules}

    def get_success_url(
        self,
        selected: SessionRule | None,
        scope: Limits,
    ) -> str:
        """Return the canonical URL for the saved rule's limits set."""
        limits_id = selected.limits_id if selected is not None else scope.pk
        return reverse("core:session_rules", args=(limits_id,))

    def get_ajax_redirect_url(
        self,
        saved: SessionRule,
        scope: Limits,
    ) -> str | None:
        """Redirect when the rule was moved to another limits set."""

        if saved.limits_id == scope.pk:
            return None

        return self.get_success_url(saved, scope)


session_rules = SessionRulesView().as_view()
