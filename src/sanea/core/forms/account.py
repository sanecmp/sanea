"""Forms for managing local account settings."""

from django import forms
from django.utils.translation import gettext_lazy as _

from ..models import Account, Person
from .base import SaneaModelForm


class AccountForm(SaneaModelForm):
    """Edit settings owned by sanea for a sanex-reported account."""

    confirm_empty_schedule = forms.BooleanField(
        required=False,
        label=_("I understand that an empty schedule blocks all sessions."),
        widget=forms.HiddenInput,
    )

    class Meta:
        model = Account
        fields = ("collect", "apply", "person")

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        self.previous_apply = self.instance.apply
        self.previous_limits_id = self.instance.limits_id
        self.fields["person"].queryset = Person.objects.select_related("limits_tpl__current_limits")
        self.fields["apply"].help_text = _("Apply the schedule and quotas. This also enables event collection.")

        if self.instance.limits_id and not self.instance.limits.ranges.filter(apply=True).exists():
            self.fields["confirm_empty_schedule"].widget = forms.CheckboxInput()

    def clean(self) -> dict:
        """Validate the prospective assignment before enabling enforcement."""
        cleaned_data = super().clean()
        person = cleaned_data.get("person")

        if person and person.pk != self.instance.person_id and person.limits_tpl_id:
            self.instance.limits = person.limits_tpl.current_limits

        if cleaned_data.get("apply"):
            cleaned_data["collect"] = True
            self.instance.collect = True
            limits = self.instance.limits

            if limits and not limits.ranges.filter(apply=True).exists():
                self.fields["confirm_empty_schedule"].widget = forms.CheckboxInput()
                enabling = not self.previous_apply or limits.pk != self.previous_limits_id

                if enabling and not cleaned_data.get("confirm_empty_schedule"):
                    self.add_error(
                        "confirm_empty_schedule",
                        _("Add allowed times to the schedule or explicitly confirm blocking all sessions."),
                    )

        return cleaned_data
