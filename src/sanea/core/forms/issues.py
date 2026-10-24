"""Issue-list filter form."""

from datetime import datetime, timedelta

from django import forms
from django.utils.translation import gettext_lazy as _

from ...utils.periods import ReportingPeriod
from ..models import Computer
from .period import PeriodFilterForm


class IssueFilterForm(PeriodFilterForm):
    """Select the computer and period shown in the issues section."""

    computer = forms.ModelChoiceField(
        label=_("Computer"),
        queryset=Computer.objects.none(),
        required=False,
        empty_label=_("All"),
    )
    PERIOD_INITIAL = ReportingPeriod.DAYS_7
    PERIOD_PRESETS = tuple(
        (period.value, period.label)
        for period in (ReportingPeriod.DAYS_7, ReportingPeriod.DAYS_30, ReportingPeriod.ALL)
    )

    field_order = ("computer", "period", "day")

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        self.fields["computer"].queryset = Computer.objects.all()

    def get_computer(self) -> Computer | None:
        """Return the validated computer selection."""

        if not self.is_valid():
            raise ValueError("issue filters must be valid")

        return self.cleaned_data["computer"]

    def get_timestamp_range(self, now: datetime) -> tuple[int | None, int | None]:
        """Return inclusive start and exclusive end, leaving rolling periods open."""

        if not self.is_valid():
            raise ValueError("issue filters must be valid")

        if bounds := self.get_selected_day_timestamps():
            return bounds

        period = ReportingPeriod(self.cleaned_data["period"])
        days = period.get_day_count()

        if days is None:
            return None, None

        return int((now - timedelta(days=days)).timestamp()), None
