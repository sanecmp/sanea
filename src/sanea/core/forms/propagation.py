"""Forms for explicitly assigning template snapshots."""

from django import forms
from django.utils.translation import gettext_lazy as _

from ..models import Account, LimitsTemplate
from .account_choices import AccountMultipleChoiceField
from .base import SaneaForm


class TemplatePropagationForm(SaneaForm):
    """Select accounts belonging to the people assigned to a template."""

    accounts = AccountMultipleChoiceField(
        label=_("Accounts"),
        queryset=Account.objects.all(),
        widget=forms.CheckboxSelectMultiple,
    )

    def __init__(self, *args: object, template: LimitsTemplate, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        queryset = Account.objects.filter(person__limits_tpl=template).select_related("computer").order_by(
            "person__name", "computer__name", "login", "pk",
        )
        accounts_field = self.fields["accounts"]
        accounts_field.queryset = queryset
        accounts_field.initial = queryset
