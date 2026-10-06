"""Forms for explicitly assigning template snapshots."""

from django import forms
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from django.db.models import QuerySet

from ..models import Account, Person
from .base import SaneaForm


class TemplatePropagationForm(SaneaForm):
    """Select a person's accounts to receive the current template snapshot."""

    accounts = forms.ModelMultipleChoiceField(
        label=_("Accounts"),
        queryset=Account.objects.all(),
        help_text=_("Selected accounts will receive the template limits."),
    )

    def __init__(self, *args: object, person: Person, **kwargs: object) -> None:
        self.person = person
        super().__init__(*args, **kwargs)
        queryset = person.accounts.select_related("computer")
        accounts_field = self.fields["accounts"]
        accounts_field.queryset = queryset
        accounts_field.initial = queryset

    def clean_accounts(self) -> QuerySet[Account]:
        """Reject account identifiers that do not belong to the person."""
        accounts = self.cleaned_data["accounts"]

        if accounts.exclude(person=self.person).exists():
            raise ValidationError(_("Every selected account must belong to this person."))

        return accounts
