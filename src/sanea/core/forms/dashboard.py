"""Shared filters for both dashboard charts."""

from datetime import datetime, timedelta

from django import forms
from django.db.models import QuerySet
from django.utils.translation import gettext_lazy as _

from ..models import Account, Person
from .period import PeriodFilterForm


class DashboardFilterForm(PeriodFilterForm):
    """Select a rolling period or calendar day and the person in both charts."""

    PERIOD_48_HOURS = "48-hours"
    PERIOD_HOURS = {"24-hours": 24, PERIOD_48_HOURS: 48, "7-days": 168, "30-days": 720}

    PERIOD_INITIAL = PERIOD_48_HOURS
    PERIOD_PRESETS = (
        ("24-hours", _("24 hours")),
        (PERIOD_48_HOURS, _("48 hours")),
        ("7-days", _("7 days")),
        ("30-days", _("30 days")),
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

        if self.cleaned_data["period"] == self.PERIOD_DAY:
            return 24

        return self.PERIOD_HOURS[self.cleaned_data["period"]]

    def get_timestamp_range(self, now: datetime) -> tuple[int, int]:
        """Return a rolling interval or the selected local calendar day's bounds."""

        if not self.is_valid():
            raise ValueError("dashboard filters must be valid")

        if bounds := self.get_selected_day_timestamps():
            return bounds

        return int((now - timedelta(hours=self.get_hour_count())).timestamp()), int(now.timestamp())

    def get_accounts(self) -> QuerySet[Account]:
        """Return collecting accounts belonging to the selected person."""

        if not self.is_valid():
            raise ValueError("dashboard filters must be valid")

        accounts = Account.objects.filter(collect=True)

        if person := self.cleaned_data["person"]:
            accounts = accounts.filter(person=person)

        return accounts
