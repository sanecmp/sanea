"""Forms for managing weekly schedule ranges."""

from django import forms
from django.utils.translation import gettext_lazy as _

from ...utils.schedule import WEEKDAY_CHOICES, format_clock, parse_clock
from ..models import Limits, Range
from .base import SaneaModelForm


class ClockField(forms.CharField):
    """Clock input stored as minutes from the beginning of a day."""

    def __init__(self, *, allow_24: bool = False, **kwargs: object) -> None:
        self.allow_24 = allow_24
        kwargs.setdefault(
            "widget",
            forms.TextInput(
                attrs={
                    "inputmode": "numeric",
                    "pattern": r"(?:[01]\d|2[0-3]):[0-5]\d" if not allow_24 else r"(?:(?:[01]\d|2[0-3]):[0-5]\d|24:00)",
                    "placeholder": "HH:MM",
                }
            ),
        )
        super().__init__(**kwargs)

    def to_python(self, value: object) -> int | None:
        value = super().to_python(value)

        if value in self.empty_values:
            return None

        try:
            return parse_clock(f"{value}", allow_24=self.allow_24)

        except ValueError as error:
            raise forms.ValidationError(
                _("Enter time as HH:MM."),
                code="invalid",
            ) from error

    def prepare_value(self, value: object) -> object:

        if isinstance(value, int):
            return format_clock(value)

        return value


class RangeForm(SaneaModelForm):
    """Edit one within-day weekly schedule interval."""

    weekday = forms.TypedChoiceField(
        label=_("Weekday"),
        choices=WEEKDAY_CHOICES,
        coerce=int,
    )
    since = ClockField(
        label=_("Start time"),
        help_text=_("Start of the allowed interval in HH:MM format."),
    )
    till = ClockField(
        label=_("End time"),
        help_text=_("Exclusive end in HH:MM format; 24:00 is allowed."),
        allow_24=True,
    )

    class Meta:
        model = Range
        fields = ("apply", "weekday", "since", "till", "session_rule")

    def __init__(self, *args: object, limits: Limits, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        self.fields["session_rule"].queryset = limits.session_rules.all()
