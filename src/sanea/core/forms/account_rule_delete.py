"""Independent confirmation for removing one saved account restriction."""

from django import forms
from django.utils.translation import gettext_lazy as _

from .base import SaneaForm


class AccountRuleDeleteForm(SaneaForm):
    """Accept only the snapshot version and explicit removal confirmations."""

    limits_version = forms.IntegerField(min_value=1, widget=forms.HiddenInput)
    confirmed = forms.BooleanField(required=False, initial=True, widget=forms.HiddenInput)
    confirm_empty_schedule = forms.BooleanField(
        required=False,
        label=_("I understand that an empty schedule blocks all sessions."),
        widget=forms.HiddenInput,
    )

    def __init__(self, *args: object, blocks_sessions: bool = False, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        self.is_submitted = self.is_bound

        if blocks_sessions:
            self.fields["confirm_empty_schedule"].widget = forms.CheckboxInput()
