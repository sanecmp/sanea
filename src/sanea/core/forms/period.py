"""Shared calendar and preset selection for reporting filters."""

import json
from datetime import date, datetime, time, timedelta

from django import forms
from django.core.validators import MaxValueValidator
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from .base import SaneaForm


class PeriodFilterForm(SaneaForm):
    """Render one calendar field with the report's own period shortcuts."""

    PERIOD_DAY = "day"
    PERIOD_PRESETS = ()
    PERIOD_INITIAL = ""

    period = forms.ChoiceField(label=_("Period"), widget=forms.HiddenInput)
    day = forms.DateField(
        label=_("Period"),
        required=False,
        input_formats=("%Y-%m-%d",),
        validators=[MaxValueValidator(date.max - timedelta(days=1))],
        widget=forms.DateInput(
            format="%Y-%m-%d",
            attrs={"type": "date", "data-period-date": "", "autocomplete": "off"},
        ),
    )

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        self.fields["period"].choices = (*self.PERIOD_PRESETS, (self.PERIOD_DAY, _("Selected day")))
        self.fields["period"].initial = self.PERIOD_INITIAL
        self.fields["day"].widget.attrs.update({
            "data-period-field": self.add_prefix("period"),
            "data-period-default": self.PERIOD_INITIAL,
            "data-period-presets": json.dumps(
                [{"value": value, "label": f"{label}"} for value, label in self.PERIOD_PRESETS], ensure_ascii=False,
            ),
        })

    def clean(self) -> dict[str, object]:
        """Accept a calendar day, including submissions without JavaScript."""
        cleaned_data = super().clean()

        if cleaned_data.get("day") is not None and "period" not in self.errors:
            cleaned_data["period"] = self.PERIOD_DAY

        if cleaned_data.get("period") == self.PERIOD_DAY and not cleaned_data.get("day") and "day" not in self.errors:
            self.add_error("day", _("Select a day."))

        return cleaned_data

    def get_selected_day_range(self) -> tuple[date, date] | None:
        """Return the selected local day as inclusive start and exclusive end."""

        if not self.is_valid():
            raise ValueError("period filters must be valid")

        if self.cleaned_data["period"] != self.PERIOD_DAY:
            return None

        day = self.cleaned_data["day"]
        return day, day + timedelta(days=1)

    def get_selected_day_timestamps(self) -> tuple[int, int] | None:
        """Return midnight bounds in sanea's timezone, respecting DST."""

        if bounds := self.get_selected_day_range():
            zone = timezone.get_current_timezone()
            return tuple(int(datetime.combine(day, time.min, zone).timestamp()) for day in bounds)

        return None
