"""Shared filters for both dashboard charts."""

from django import forms
from django.db.models import QuerySet
from django.utils.translation import gettext_lazy as _

from ..models import Account, Person
from .base import SaneaForm


class DashboardFilterForm(SaneaForm):
    """Select a rolling period and the person shown in both charts."""

    PERIOD_48_HOURS = "48-hours"
    PERIOD_HOURS = {"24-hours": 24, PERIOD_48_HOURS: 48, "7-days": 168, "30-days": 720}

    period = forms.ChoiceField(
        label=_("Period"),
        choices=(
            ("24-hours", _("24 hours")),
            (PERIOD_48_HOURS, _("48 hours")),
            ("7-days", _("7 days")),
            ("30-days", _("30 days")),
        ),
        initial=PERIOD_48_HOURS,
    )
    person = forms.ModelChoiceField(
        label=_("Person"),
        queryset=Person.objects.none(),
        required=False,
        empty_label=_("All"),
    )

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        self.fields["person"].queryset = Person.objects.order_by("name", "pk")

    def get_hour_count(self) -> int:
        """Return the duration of the selected rolling window in hours."""

        if not self.is_valid():
            raise ValueError("dashboard filters must be valid")

        return self.PERIOD_HOURS[self.cleaned_data["period"]]

    def get_accounts(self) -> QuerySet[Account]:
        """Return collecting accounts belonging to the selected person."""

        if not self.is_valid():
            raise ValueError("dashboard filters must be valid")

        accounts = Account.objects.filter(collect=True)

        if person := self.cleaned_data["person"]:
            accounts = accounts.filter(person=person)

        return accounts
