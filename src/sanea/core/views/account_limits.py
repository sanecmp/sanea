"""Child-centered restrictions card scoped to one computer account."""

from django import forms
from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.http import Http404, HttpRequest, HttpResponse, HttpResponseNotAllowed
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from ...utils.schedule import WEEKDAY_CHOICES, format_clock
from ..forms.account_limits import AccountLimitsForm
from ..forms.account_rule_delete import AccountRuleDeleteForm
from ..models import Account, AppRule, Range, SessionRule
from .base import ManagedView


def build_rule_deletion(account: Account, kind: str, rule: SessionRule | Range | AppRule) -> dict[str, object]:
    """Describe one saved rule's scope and removal consequences."""
    title = (
        f"{WEEKDAY_CHOICES[rule.weekday][1]}, {format_clock(rule.since)}–{format_clock(rule.till)}"
        if isinstance(rule, Range) else rule.name
    )
    related_ranges = rule.ranges.count() if isinstance(rule, SessionRule) else 0
    related_apps = rule.app_rules.count() if isinstance(rule, SessionRule) else 0
    blocks_sessions = account.should_confirm_rule_removal(rule)
    confirmation = (
        _("Remove preset “%(title)s” and its %(ranges)s intervals and %(apps)s application rules?")
        % {"title": title, "ranges": related_ranges, "apps": related_apps}
        if isinstance(rule, SessionRule) else _("Remove “%(title)s”?") % {"title": title}
    )

    if blocks_sessions:
        confirmation = f"{confirmation} {_("This leaves no allowed intervals and blocks all sessions on this account.")}"

    return {
        "kind": kind, "rule_pk": rule.pk, "form_id": f"account-remove-{kind}-{rule.pk}", "title": title,
        "related_ranges": related_ranges, "related_apps": related_apps,
        "blocks_sessions": blocks_sessions, "confirmation": confirmation,
    }


class AccountLimitsView(ManagedView):
    """Save schedule, sessions and applications together without AJAX state."""

    def dispatch(self, request: HttpRequest, **kwargs: object) -> HttpResponse:
        """Show the account editor and save all restriction tabs together."""
        account = get_object_or_404(
            Account.objects.select_related("computer", "person", "limits"), pk=kwargs["account_pk"],
        )
        form = AccountLimitsForm(request.POST if request.method == "POST" else None, account=account)

        if request.method == "POST" and form.is_valid():
            try:
                Account.save_limits_form(form)

            except ValidationError as error:
                form.add_error(None, error.messages)

            else:
                return redirect(f"{reverse('core:account_limits', args=(account.pk,))}?saved=1")

        choices = (
            Account.objects.filter(person_id=account.person_id).select_related("computer")
            if account.person_id else Account.objects.filter(pk=account.pk).select_related("computer")
        )
        return render(request, "sanea/accounts/limits.html", {
            "page_title": account.person.name if account.person_id else account.name or account.login,
            "account": account,
            "account_choices": tuple(choices),
            "limits_form": form,
            "deletion_forms": tuple(
                build_rule_deletion(account, kind, rule)
                for kind in ("sessions", "ranges", "apps")
                for rule in (
                    account.get_limits_rules(kind).prefetch_related("ranges", "app_rules")
                    if kind == "sessions" else account.get_limits_rules(kind)
                )
            ),
            "message": (
                _("Restriction removed.") if request.GET.get("removed")
                else _("Account settings saved.") if request.GET.get("saved") else ""
            ),
        })


class AccountRuleDeleteView(ManagedView):
    """Confirm and atomically remove one rule independently of the editor."""

    def dispatch(self, request: HttpRequest, **kwargs: object) -> HttpResponse:
        """Confirm one rule removal and reject stale graph versions."""

        if request.method not in ("GET", "POST"):
            return HttpResponseNotAllowed(("GET", "POST"))

        kind = kwargs["kind"]

        if kind not in ("sessions", "ranges", "apps"):
            raise Http404

        account = get_object_or_404(
            Account.objects.select_related("computer", "person", "limits"), pk=kwargs["account_pk"],
        )
        form = AccountRuleDeleteForm(
            request.POST if request.method == "POST" else None, initial={"limits_version": account.limits_id},
        )
        confirmed = form.fields["confirmed"].clean(request.POST.get("confirmed")) if request.method == "POST" else False
        validate_submission = request.method == "POST" and (confirmed or request.POST.get("limits_version"))
        status = 200

        if validate_submission:
            form.is_valid()
            version = form.cleaned_data.get("limits_version")

            if version is not None and version != account.limits_id:
                form.add_error(None, _("The rules changed. Reload the card before removing a rule."))
                return render(request, "sanea/accounts/delete_rule.html", {
                    "account": account, "deletion": {"kind": kind, "rule_pk": kwargs["rule_pk"]}, "removal_form": form,
                }, status=409)

        rule = get_object_or_404(account.get_limits_rules(kind), pk=kwargs["rule_pk"])
        deletion = build_rule_deletion(account, kind, rule)

        if deletion["blocks_sessions"]:
            form.fields["confirm_empty_schedule"].widget = forms.CheckboxInput()

        if confirmed and form.is_valid():
            try:
                account.remove_limits_rule(
                    kind, rule.pk, limits_version=form.cleaned_data["limits_version"],
                    confirm_empty_schedule=form.cleaned_data["confirm_empty_schedule"],
                )

            except ObjectDoesNotExist as error:
                raise Http404 from error

            except ValidationError as error:
                form.add_error(None, error.messages)
                status = 409 if getattr(error, "code", None) == "stale_limits" else 200

            else:
                return redirect(f"{reverse('core:account_limits', args=(account.pk,))}?removed=1")

        elif not confirmed and (not validate_submission or not form.errors):
            form = AccountRuleDeleteForm(
                initial={"limits_version": account.limits_id}, blocks_sessions=deletion["blocks_sessions"],
            )

        return render(request, "sanea/accounts/delete_rule.html", {
            "account": account, "deletion": deletion, "removal_form": form,
        }, status=status)


account_limits = AccountLimitsView().as_view()
account_rule_delete = AccountRuleDeleteView().as_view()
