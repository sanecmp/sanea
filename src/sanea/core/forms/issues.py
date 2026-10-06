"""Issue-list filter form."""

from datetime import datetime, timedelta

from django import forms
from django.utils.translation import gettext_lazy as _

from ...utils.periods import ReportingPeriod
from ..models import Computer
from .base import SaneaForm


class IssueFilterForm(SaneaForm):
    """Select the computer and period shown in the issues section."""

    computer = forms.ModelChoiceField(
        label=_("Computer"),
        queryset=Computer.objects.none(),
        required=False,
        empty_label=_("All computers"),
    )
    period = forms.ChoiceField(
        label=_("Period"),
        choices=tuple(
            (period.value, period.label)
            for period in (
                ReportingPeriod.DAYS_7,
                ReportingPeriod.DAYS_30,
                ReportingPeriod.ALL,
            )
        ),
        initial=ReportingPeriod.DAYS_7,
    )

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        self.fields["computer"].queryset = Computer.objects.all()

    def get_computer(self) -> Computer | None:
        """Return the validated computer selection."""

        if not self.is_valid():
            raise ValueError("issue filters must be valid")

        return self.cleaned_data["computer"]

    def get_since(self, now: datetime) -> int | None:
        """Return the inclusive Unix timestamp boundary for the selected period."""

        if not self.is_valid():
            raise ValueError("issue filters must be valid")

        period = ReportingPeriod(self.cleaned_data["period"])
        days = period.get_day_count()

        if days is None:
            return None

        return int((now - timedelta(days=days)).timestamp())
