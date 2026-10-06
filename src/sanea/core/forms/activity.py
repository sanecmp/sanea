"""Activity report filter form."""

from datetime import date, timedelta

from django import forms
from django.core.exceptions import ValidationError
from django.db.models import QuerySet
from django.utils.translation import gettext_lazy as _

from ...utils.periods import ReportingPeriod
from ..models import Account, Computer, Person
from .base import SaneaForm


class ActivityFilterForm(SaneaForm):
    """Select the monitored accounts and local-date reporting period."""

    PERIOD_TODAY = ReportingPeriod.TODAY
    PERIOD_7_DAYS = ReportingPeriod.DAYS_7
    PERIOD_30_DAYS = ReportingPeriod.DAYS_30

    person = forms.ModelChoiceField(
        label=_("User"),
        queryset=Person.objects.none(),
        required=False,
        empty_label=_("All users"),
    )
    computer = forms.ModelChoiceField(
        label=_("Computer"),
        queryset=Computer.objects.none(),
        required=False,
        empty_label=_("All computers"),
    )
    account = forms.ModelChoiceField(
        label=_("Account"),
        queryset=Account.objects.none(),
        required=False,
        empty_label=_("All accounts"),
    )
    period = forms.ChoiceField(
        label=_("Period"),
        choices=tuple(
            (period.value, period.label)
            for period in (
                ReportingPeriod.TODAY,
                ReportingPeriod.DAYS_7,
                ReportingPeriod.DAYS_30,
            )
        ),
        initial=PERIOD_TODAY,
    )

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        monitored_accounts = Account.objects.filter(collect=True)
        fields = self.fields
        fields["person"].queryset = Person.objects.filter(
            accounts__in=monitored_accounts
        ).distinct()
        fields["computer"].queryset = Computer.objects.filter(
            accounts__in=monitored_accounts
        ).distinct()
        fields["account"].queryset = monitored_accounts.select_related(
            "computer",
            "person",
        )

    def clean(self) -> dict[str, object]:
        """Reject an account outside the selected user or computer."""
        cleaned_data = super().clean()
        account = cleaned_data.get("account")
        person = cleaned_data.get("person")
        computer = cleaned_data.get("computer")

        if account is not None:

            if person is not None and account.person_id != person.pk:
                self.add_error(
                    "account",
                    ValidationError(_("The account does not belong to this user.")),
                )

            if computer is not None and account.computer_id != computer.pk:
                self.add_error(
                    "account",
                    ValidationError(_("The account does not belong to this computer.")),
                )

        return cleaned_data

    def get_accounts(self) -> QuerySet[Account]:
        """Return monitored accounts matching the validated selections."""

        if not self.is_valid():
            raise ValueError("activity filters must be valid")

        accounts = Account.objects.filter(collect=True)
        cleaned_data = self.cleaned_data
        person = cleaned_data["person"]
        computer = cleaned_data["computer"]
        account = cleaned_data["account"]

        if person is not None:
            accounts = accounts.filter(person=person)

        if computer is not None:
            accounts = accounts.filter(computer=computer)

        if account is not None:
            accounts = accounts.filter(pk=account.pk)

        return accounts

    def get_date_range(self, today: date) -> tuple[date, date]:
        """Return an inclusive start and exclusive end for the selected period."""

        if not self.is_valid():
            raise ValueError("activity filters must be valid")

        period = ReportingPeriod(self.cleaned_data["period"])
        days = period.get_day_count()

        if days is None:
            raise ValueError("activity period must have a day count")

        return today - timedelta(days=days - 1), today + timedelta(days=1)
