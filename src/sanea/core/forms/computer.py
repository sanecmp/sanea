"""Form for managing one registered computer."""

from zoneinfo import available_timezones

from django import forms
from django.utils.translation import gettext_lazy as _
from siteforms.composers.base import FORM

from ..models import Computer, ComputerStatus
from .base import GridModelForm


def _get_timezone_choices() -> tuple[tuple[str, str], ...]:
    return tuple((name, name) for name in sorted(available_timezones()))


class ComputerForm(GridModelForm):
    """Edit access, timezone and sanex runtime intervals for one computer."""

    status = forms.ChoiceField(
        label=_("Synchronization"),
        choices=(
            (ComputerStatus.ALLOWED, _("Synchronization allowed")),
            (ComputerStatus.BLOCKED, _("Synchronization blocked")),
        ),
        help_text=_("Blocking synchronization stops settings and data exchange, not computer use."),
    )

    timezone = forms.ChoiceField(
        label=_("Timezone"),
        choices=_get_timezone_choices,
    )

    class Composer(GridModelForm.Composer):
        layout = {FORM: {"computer": [
            ("name", "status"), "timezone", ("sync_interval", "discovery_interval"),
            ("walk_interval", "save_interval", "min_prc_duration"),
        ]}}

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
        labels = {
            "sync_interval": _("Sync interval, sec"),
            "discovery_interval": _("Discovery interval, sec"),
            "walk_interval": _("Scan interval, sec"),
            "save_interval": _("Save interval, sec"),
            "min_prc_duration": _("Minimum app duration, sec"),
        }
        help_texts = dict.fromkeys(fields, "")
