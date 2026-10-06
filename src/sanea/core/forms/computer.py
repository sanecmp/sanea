"""Form for managing one registered computer."""

from zoneinfo import available_timezones

from django import forms
from django.utils.translation import gettext_lazy as _

from ..models import Computer, ComputerStatus
from .base import SaneaModelForm


def _get_timezone_choices() -> tuple[tuple[str, str], ...]:
    return tuple((name, name) for name in sorted(available_timezones()))


class ComputerForm(SaneaModelForm):
    """Edit access, timezone and sanex runtime intervals for one computer."""

    status = forms.ChoiceField(
        label=_("Access"),
        choices=(
            (ComputerStatus.ALLOWED, ComputerStatus.ALLOWED.label),
            (ComputerStatus.BLOCKED, ComputerStatus.BLOCKED.label),
        ),
        help_text=_("Blocked computers cannot synchronize or upload data."),
    )

    timezone = forms.ChoiceField(
        label=_("Timezone"),
        choices=_get_timezone_choices,
        help_text=_("IANA timezone used to evaluate weekly schedules."),
    )

    class Meta:
        model = Computer
        fields = (
            "name",
            "status",
            "timezone",
            "sync_interval",
            "discovery_interval",
            "walk_interval",
            "save_interval",
            "min_prc_duration",
        )
