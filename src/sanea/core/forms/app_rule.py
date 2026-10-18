"""Forms for managing application rules."""

from collections import Counter

from django import forms
from django.db.models import QuerySet
from django.utils.translation import gettext_lazy as _
from siteforms.composers.base import FORM

from ..models import ActivityEvent, AppRule
from .activity_suggestions import RecognitionSuggestion, get_activity_suggestions
from .base import GridModelForm


def get_app_suggestions(events: QuerySet[ActivityEvent]) -> dict[str, tuple[RecognitionSuggestion, ...]]:
    """Offer recent recognition values from an explicitly scoped event set."""
    return {
        field_name: get_activity_suggestions(
            events, field_name, max_length=AppRule._meta.get_field(field_name).max_length,
            name_field="app_name" if field_name == "app_id" else None,
        )
        for field_name in ("app_id", "prc_name", "exe")
    }


class AppRuleForm(GridModelForm):
    """Edit application quotas and recognition conditions."""

    class Composer(GridModelForm.Composer):
        wrappers = {
            "recognition": (
                "<fieldset class=\"mt-2 pt-3 border-top\"><legend class=\"h6 mb-3\">{title}</legend>{rows}</fieldset>"
            ),
        }
        layout = {FORM: {
            "enabled": ["apply"],
            "identity": ["name"],
            "quotas": [("max_launches", "max_time")],
            "recognition": [
                "app_id",
                ("prc_name", "prc_name_match"),
                ("exe", "exe_match"),
                ("wnd_title", "wnd_title_match"),
            ],
        }}
        groups = {"recognition": _("Recognition conditions")}

    def __init__(
        self,
        *args: object,
        suggestions: dict[str, tuple[RecognitionSuggestion, ...]] | None = None,
        **kwargs: object,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.suggestions: dict[str, tuple[RecognitionSuggestion, ...]] = {}
        suggestions = suggestions or {}
        applications = suggestions.get("app_id", ())
        names = Counter(application.name for application in applications if application.name)
        choices = {}

        for application in applications:
            name = application.name or application.value

            if names[name] > 1:
                name = f"{name} ({application.value})"

            choices[application.value] = name

        if not applications:
            self.fields["app_id"].help_text = _("No applications in statistics yet. Use the conditions below.")

        selected = self["app_id"].value()

        if selected and selected not in choices:
            choices[selected] = selected

        self.fields["app_id"].widget.choices = [("", _("Not selected")), *choices.items()]

        for field_name in ("prc_name_match", "exe_match", "wnd_title_match"):
            field = self.fields[field_name]
            field.widget.attrs["aria-label"] = field.label
            field.label = _("Comparison")

        for field_name, values in suggestions.items():

            if field_name != "app_id" and values:
                datalist_id = f"{self[field_name].auto_id}-suggestions"
                self.fields[field_name].widget.attrs["list"] = datalist_id
                self.suggestions[datalist_id] = values

    class Meta:
        model = AppRule
        labels = {"app_id": _("Application")}
        widgets = {"app_id": forms.Select(attrs={"data-select-search": "always"})}
        help_texts = {"app_id": _("From recorded activity. Optional.")}
        fields = (
            "name",
            "apply",
            "max_launches",
            "max_time",
            "app_id",
            "prc_name",
            "prc_name_match",
            "exe",
            "exe_match",
            "wnd_title",
            "wnd_title_match",
        )
