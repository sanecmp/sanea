"""One validated editor for an account's schedule and quota graph."""

from decimal import Decimal

from django import forms
from django.forms import BaseModelFormSet, modelformset_factory
from django.utils.translation import gettext_lazy as _
from siteforms.composers.base import ALL_FIELDS, ALL_GROUPS, ALL_ROWS, FORM

from ..models import Account, ActivityEvent, AppRule, Range, SessionRule
from .app_rule import AppRuleForm, get_app_suggestions
from .base import SaneaForm, SaneaModelForm
from .range import RangeForm
from .session_rule import SessionRuleForm


class AccountLimitsComposer(SaneaModelForm.Composer):
    """Keep native Bootstrap field rendering inside the card's layout."""

    wrappers = {
        ALL_FIELDS: "<div class=\"sanea-limits-field\">{field}</div>",
        ALL_ROWS: "{fields}",
        ALL_GROUPS: "<div class=\"sanea-limits-fields\">{rows}</div>",
        "deletion": "<div data-delete-field hidden>{rows}</div>",
        "_hidden": "{rows}",
    }
    attrs_feedback = {
        **SaneaModelForm.Composer.attrs_feedback,
        FORM: {
            **SaneaModelForm.Composer.attrs_feedback[FORM],
            "data-limits-error": "1",
        },
        ALL_FIELDS: {
            **SaneaModelForm.Composer.attrs_feedback[ALL_FIELDS],
            "data-limits-error": "1", "role": "alert",
        },
    }


class MinutesField(forms.IntegerField):
    """Display minutes while retaining the model's second precision."""

    def __init__(self, **kwargs: object) -> None:
        kwargs.setdefault("min_value", 0)
        kwargs.setdefault("widget", forms.NumberInput(attrs={"step": "any"}))
        super().__init__(**kwargs)

    def to_python(self, value: object) -> int | None:
        minutes = forms.DecimalField(min_value=0, max_digits=30).clean(value) if value not in self.empty_values else None
        return None if minutes is None else int((minutes * 60).to_integral_value())

    def prepare_value(self, value: object) -> object:

        if isinstance(value, int):
            return Decimal(value) / 60

        return value


class AccountSessionForm(SessionRuleForm):
    """Reuse session validation with parent-facing duration units."""

    max_duration = MinutesField(
        required=False, label=_("Session, min"),
        help_text=_("Duration of one session. Empty means unlimited."),
    )
    break_duration = MinutesField(
        label=_("Break, min"), help_text=_("Zero means no break."),
        initial=SessionRule._meta.get_field("break_duration").get_default(),
    )

    class Composer(AccountLimitsComposer):
        layout = {FORM: {
            "rules": ("name", "apply", "max_sessions", "max_duration", "break_duration"),
            "deletion": ("DELETE",),
        }}

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        self.is_submitted = self.is_bound
        self.fields["name"].help_text = ""
        self.fields["apply"].label = _("Enabled rule")
        self.fields["apply"].help_text = ""
        self.fields["max_sessions"].label = _("Sessions per interval")
        self.fields["max_sessions"].help_text = _("Per allowed interval. Empty means unlimited.")


class AccountRangeForm(RangeForm):
    """Reference a submitted session row, including a newly added one."""

    rule = forms.ChoiceField(label=_("Session preset"))

    class Meta(RangeForm.Meta):
        fields = ("apply", "weekday", "since", "till")

    class Composer(AccountLimitsComposer):
        layout = {FORM: {
            "rules": ("apply", "weekday", "since", "till", "rule"),
            "deletion": ("DELETE",),
        }}

    def __init__(
        self, *args: object, rules: tuple[tuple[str, str], ...],
        rule_rows: dict[int, str], **kwargs: object,
    ) -> None:
        SaneaModelForm.__init__(self, *args, **kwargs)
        self.is_submitted = self.is_bound
        self.fields["rule"].choices = rules
        self.fields["weekday"].choices = (("", _("Choose day")), *self.fields["weekday"].choices)
        self.fields["apply"].label = _("Allowed")
        self.fields["apply"].help_text = ""
        self.fields["weekday"].label = _("Day")
        self.fields["since"].label = _("Start")
        self.fields["since"].help_text = ""
        self.fields["till"].label = _("End")
        self.fields["till"].help_text = _("24:00 is allowed.")
        self.initial["rule"] = rule_rows.get(self.instance.session_rule_id, "")
        # Validate the proposed graph together, not against its old intervals.
        self.instance.limits_id = None
        self.instance.session_rule_id = None

    def clean(self) -> dict[str, object]:
        cleaned_data = super().clean()
        since = cleaned_data.get("since")
        till = cleaned_data.get("till")

        if since is not None and till is not None and since >= till:
            self.add_error("till", _("End time must be later than start time."))

        return cleaned_data


class AccountAppForm(AppRuleForm):
    """Reuse application recognition validation within the common editor."""

    rule = forms.ChoiceField(label=_("Session preset"))
    max_time = MinutesField(
        required=False, label=_("Usage, min"),
        help_text=_("Total application time in one allowed interval. Empty means unlimited."),
    )

    class Composer(AccountLimitsComposer):
        layout = {FORM: {
            "rules": ("name", "apply", "max_launches", "max_time", "prc_name", "rule"),
            "recognition": ("prc_name_match", "exe", "exe_match", "wnd_title", "wnd_title_match"),
            "deletion": ("DELETE",),
        }}
        groups = {"recognition": _("Advanced recognition")}
        wrappers = {
            "recognition": (
                "<details class=\"sanea-limits-recognition mt-3\"><summary>{title}</summary>"
                "<div class=\"sanea-limits-fields mt-2\">{rows}</div></details>"
            ),
        }

    def __init__(
        self, *args: object, rules: tuple[tuple[str, str], ...],
        rule_rows: dict[int, str], **kwargs: object,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.fields["rule"].choices = rules
        self.is_submitted = self.is_bound
        self.fields["apply"].label = _("Enabled rule")
        self.fields["apply"].help_text = ""
        self.fields["max_launches"].label = _("Launches per interval")
        self.fields["max_launches"].help_text = _("Per allowed interval. Empty means unlimited.")
        self.fields["name"].help_text = ""
        self.fields["prc_name"].label = _("Process")
        self.fields["prc_name"].help_text = _("Exact process name unless another matching method is chosen below.")
        self.initial["rule"] = rule_rows.get(self.instance.session_rule_id, "")
        self.instance.session_rule_id = None
        self._bound_fields_cache.clear()

    def clean(self) -> dict[str, object]:
        cleaned_data = super().clean()

        if cleaned_data.get("prc_name") and not cleaned_data.get("prc_name_match"):
            cleaned_data["prc_name_match"] = "exact"

        return cleaned_data


class AccountRuleFormSet(BaseModelFormSet):
    """Keep submitted row identities within the selected account graph."""

    def add_fields(self, form: SaneaModelForm, index: int | None) -> None:
        super().add_fields(form, index)
        form.fields["id"].queryset = self.get_queryset()
        form.fields["DELETE"].label = _("Remove")

    def clean(self) -> None:
        expected_ids = set(self.get_queryset().values_list("pk", flat=True))
        submitted_ids = [form.instance.pk for form in self.initial_forms]

        if (
            self.initial_form_count() != len(expected_ids)
            or len(submitted_ids) != len(expected_ids)
            or set(submitted_ids) != expected_ids
            or any(self.data.get(f"{form.prefix}-id") for form in self.extra_forms)
        ):
            raise forms.ValidationError(_("The rules changed. Reload the card before saving."))

        super().clean()


class AccountRangeFormSet(AccountRuleFormSet):
    """Check overlap between all prospective allowed intervals."""

    def clean(self) -> None:
        super().clean()

        if any(self.errors):
            return

        intervals = sorted(
            (
                (form.cleaned_data["weekday"], form.cleaned_data["since"], form.cleaned_data["till"])
                for form in self.forms
                if form.cleaned_data and not form.cleaned_data.get("DELETE") and form.cleaned_data.get("apply")
            ),
        )

        for previous, current in zip(intervals, intervals[1:]):

            if previous[0] == current[0] and current[1] < previous[2]:
                raise forms.ValidationError(_("Applied ranges must not overlap."))


SessionFormSet = modelformset_factory(
    SessionRule, form=AccountSessionForm, formset=AccountRuleFormSet, extra=1, can_delete=True,
)
RangeFormSet = modelformset_factory(
    Range, form=AccountRangeForm, formset=AccountRangeFormSet, extra=1, can_delete=True,
)
AppFormSet = modelformset_factory(
    AppRule, form=AccountAppForm, formset=AccountRuleFormSet, extra=1, can_delete=True,
)


class AccountLimitsForm(SaneaForm):
    """Validate all three tabs before writing any account configuration."""

    collect = forms.BooleanField(required=False, label=_("Monitoring"))
    apply = forms.BooleanField(
        required=False, label=_("Limits"),
        help_text=_("Apply the schedule and quotas. This also enables event collection."),
    )
    confirm_empty_schedule = forms.BooleanField(
        required=False, label=_("I understand that an empty schedule blocks all sessions."),
        help_text=_("Enabling limits with no active intervals blocks all computer use for this account."),
    )
    limits_version = forms.CharField(required=False, max_length=20, widget=forms.HiddenInput)

    class Composer(AccountLimitsComposer):
        layout = {FORM: {
            "controls": ("collect", "apply"),
            "caution": ("confirm_empty_schedule",),
        }}
        groups = {"caution": _("Empty schedule")}
        wrappers = {
            "controls": "<div class=\"sanea-limits-controls mb-4\">{rows}</div>",
            "caution": "<details class=\"sanea-limits-caution mb-4\"><summary>{title}</summary>{rows}</details>",
        }

    def __init__(self, *args: object, account: Account, **kwargs: object) -> None:
        self.account = account
        kwargs.setdefault("prefix", "limits")
        kwargs.setdefault("initial", {
            "collect": account.collect, "apply": account.apply,
            "limits_version": f"{account.limits_id}" if account.limits_id else "",
        })
        super().__init__(*args, **kwargs)
        data = self.data if self.is_bound else None
        self.is_submitted = self.is_bound
        sessions = SessionRule.objects.filter(limits_id=account.limits_id).order_by("pk")
        ranges = Range.objects.filter(limits_id=account.limits_id).order_by("pk")
        apps = AppRule.objects.filter(session_rule__limits_id=account.limits_id).order_by("pk")
        rule_rows = {rule.pk: f"{index}" for index, rule in enumerate(sessions)}
        self.sessions = SessionFormSet(data, queryset=sessions, prefix="sessions")
        choices = (("", _("Choose preset")),) + tuple(
            (f"{index}", f"{form['name'].value() or _('New preset')}")
            for index, form in enumerate(self.sessions.forms)
            if not form["DELETE"].value()
        )
        form_kwargs = {"rules": choices, "rule_rows": rule_rows}
        self.ranges = RangeFormSet(data, queryset=ranges, prefix="ranges", form_kwargs=form_kwargs)
        suggestions = get_app_suggestions(ActivityEvent.objects.filter(account=account, type="prc_start"))
        self.apps = AppFormSet(
            data, queryset=apps, prefix="apps", form_kwargs={**form_kwargs, "suggestions": suggestions},
        )
        self.requires_empty_confirmation = not ranges.filter(apply=True).exists()

    def get_composer(self) -> AccountLimitsComposer:
        composer = super().get_composer()

        if self.requires_empty_confirmation:
            composer.wrappers = {
                **composer.wrappers,
                "caution": composer.wrappers["caution"].replace("<details ", "<details open ", 1),
            }

        return composer

    def clean(self) -> dict[str, object]:
        cleaned_data = super().clean()
        valid_tabs = (self.sessions.is_valid(), self.ranges.is_valid(), self.apps.is_valid())
        source_version = f"{self.account.limits_id}" if self.account.limits_id else ""

        if cleaned_data.get("limits_version", "") != source_version:
            self.add_error("limits_version", _("The rules changed. Reload the card before saving."))

        if not all(valid_tabs):
            raise forms.ValidationError(_("Check the highlighted fields in the tabs."))

        session_rows = {
            f"{index}" for index, form in enumerate(self.sessions.forms)
            if form.cleaned_data and not form.cleaned_data.get("DELETE")
        }

        for formset in (self.ranges, self.apps):

            for form in formset.forms:
                values = form.cleaned_data

                if values and not values.get("DELETE") and values.get("rule") not in session_rows:
                    form.add_error("rule", _("Choose a preset that is not empty or removed."))
                    self.add_error(None, _("Check the highlighted fields in the tabs."))

        if cleaned_data.get("apply"):
            cleaned_data["collect"] = True
            has_allowed_times = any(
                form.cleaned_data.get("apply") and not form.cleaned_data.get("DELETE")
                for form in self.ranges.forms
            )
            had_allowed_times = not self.requires_empty_confirmation
            self.requires_empty_confirmation = not has_allowed_times

            if not has_allowed_times and (not self.account.apply or had_allowed_times):

                if not cleaned_data.get("confirm_empty_schedule"):
                    self.add_error(
                        "confirm_empty_schedule",
                        _("Add allowed times to the schedule or explicitly confirm blocking all sessions."),
                    )

        return cleaned_data

    def has_graph_changes(self) -> bool:
        """Ignore untouched or discarded extra rows when copying limits."""
        return any(
            form.has_changed()
            for formset in (self.sessions, self.ranges, self.apps)
            for form in formset.forms
            if form.instance.pk is not None or not form.cleaned_data.get("DELETE")
        )
