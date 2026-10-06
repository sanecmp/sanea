"""Application rule management views."""

from dataclasses import dataclass

from django.db.models import QuerySet
from django.http import HttpRequest
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from ..forms import AppRuleForm
from ..models import AppRule, Limits, SessionRule
from .editor import ModelEditorView


@dataclass(frozen=True, slots=True)
class AppRuleScope:
    """Validated parents of one nested application-rule request."""

    limits: Limits
    session_rule: SessionRule


class AppRulesView(ModelEditorView[AppRuleScope, AppRule, AppRuleForm]):
    """List and edit application rules belonging to one session rule."""

    page_title = _("Application rules")
    section = "app_rules"
    editor_id = "app-rule-editor"
    editor_template = "sanea/app_rules/_editor.html"
    reference_name = "app_rule"
    selected_context_name = "app_rule"
    form_context_name = "app_rule_form"
    url_context_name = "app_rules_url"
    saved_message = _("Application rule saved.")
    add_trigger = "app-rule-add"
    edit_trigger = "app-rule-edit-*"
    save_trigger = "app-rule-save"
    cancel_trigger = "app-rule-cancel"

    def get_scope(self, **kwargs: object) -> AppRuleScope:
        """Resolve and validate both nested parent objects."""
        limits = get_object_or_404(Limits, pk=kwargs["limits_pk"])
        session_rule = get_object_or_404(
            SessionRule,
            pk=kwargs["rule_pk"],
            limits=limits,
        )
        return AppRuleScope(limits, session_rule)

    def build_form(
        self,
        request: HttpRequest,
        scope: AppRuleScope,
    ) -> tuple[AppRule | None, AppRuleForm]:
        """Build a form for a selected or new application rule."""
        reference = request.POST.get("app_rule", request.GET.get("app_rule", ""))
        selected = None

        if reference and reference != "new":
            selected = get_object_or_404(
                AppRule,
                session_rule=scope.session_rule,
                pk=reference,
            )

        form = AppRuleForm(
            request=request,
            src="POST",
            prefix="app_rule",
            instance=selected,
            render_form_tag=False,
        )
        return selected, form

    def save_form(
        self,
        form: AppRuleForm,
        selected: AppRule | None,
        scope: AppRuleScope,
    ) -> AppRule:
        """Persist an application rule through its model API."""
        return AppRule.save_form(form, scope.session_rule)

    def get_scope_context(self, scope: AppRuleScope) -> dict[str, object]:
        """Expose both nested parents to all templates."""
        return {
            "limits": scope.limits,
            "session_rule": scope.session_rule,
        }

    def get_list_context(self, scope: AppRuleScope) -> dict[str, object]:
        """Return the application rules for the list fragment."""
        app_rules: QuerySet[AppRule] = AppRule.objects.filter(
            session_rule=scope.session_rule
        )
        return {"app_rules": app_rules}

    def get_success_url(
        self,
        selected: AppRule | None,
        scope: AppRuleScope,
    ) -> str:
        """Return the canonical URL for the saved rule's parents."""
        session_rule = (
            selected.session_rule if selected is not None else scope.session_rule
        )
        return reverse(
            "core:app_rules",
            args=(session_rule.limits_id, session_rule.pk),
        )

    def get_ajax_redirect_url(
        self,
        saved: AppRule,
        scope: AppRuleScope,
    ) -> str | None:
        """Redirect when the rule was moved outside the current limits set."""

        if saved.session_rule.limits_id == scope.limits.pk:
            return None

        return self.get_success_url(saved, scope)


app_rules = AppRulesView().as_view()
