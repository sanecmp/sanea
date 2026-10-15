"""Read-only computer details grouped by purpose."""

from django import forms
from django.forms.utils import flatatt
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from siteforms.composers.base import ALL_FIELDS, ALL_GROUPS, FIELDS_READONLY, FORM
from siteforms.widgets import ReadOnlyWidget

from ..models import ComputerStatus
from .computer import ComputerForm


class ComputerReadOnlyWidget(ReadOnlyWidget):
    """Escape computer-reported text before siteforms marks the form safe."""

    @classmethod
    def wrap_value(cls, *, value: object, attrs: dict[str, object]) -> str:
        """Render plain text, including untrusted hostnames and display names."""
        display = "—" if value is None or value == "" else value
        return format_html("<div{}>{}</div>", flatatt(attrs), display)


class ComputerDetailsForm(ComputerForm):
    """Show settings and reported information without editable controls."""

    readonly_fields = "__all__"
    status = forms.ChoiceField(
        label=_("Synchronization"),
        choices=(
            (ComputerStatus.PENDING, _("Pending")),
            (ComputerStatus.ALLOWED, _("Synchronization allowed")),
            (ComputerStatus.BLOCKED, _("Synchronization blocked")),
        ),
    )
    connection = forms.CharField(label=_("Connection"))
    configuration = forms.CharField(label=_("Configuration"))
    offered_config = forms.IntegerField(label=_("Offered settings"))
    confirmed_config = forms.IntegerField(label=_("Confirmed settings"))
    pending_commands = forms.IntegerField(label=_("Pending commands"))

    class Composer(ComputerForm.Composer):
        opt_render_help = False
        opt_label_colon = False
        attrs = {
            ALL_GROUPS: {"class": "mb-3 pb-1 border-bottom"},
            "technical": {"class": "mb-0"},
            FIELDS_READONLY: {"class": "form-control-plaintext py-0 text-break"},
        }
        attrs_labels = {ALL_FIELDS: {"class": "small text-body-secondary mb-1"}}
        groups = {
            "computer": _("Computer"),
            "state": _("State"),
            "intervals": _("Intervals"),
            "technical": _("Technical details"),
        }
        wrappers = {
            ALL_FIELDS: '<div class="col-12 col-sm-6 mb-3">{field}</div>',
            ALL_GROUPS: '<fieldset{attrs}><legend class="h6 fw-semibold mb-3">{title}</legend>{rows}</fieldset>',
            **dict.fromkeys(
                ("status", "connection", "configuration", "last_seen", "last_ip", "pending_commands"),
                '<div class="col-12 col-sm-4 mb-3">{field}</div>',
            ),
        }
        layout = {FORM: {
            "computer": [("name", "hostname"), ("version", "timezone")],
            "state": [("status", "connection", "configuration"), ("last_seen", "last_ip", "pending_commands")],
            "intervals": [
                ("sync_interval", "discovery_interval"), ("walk_interval", "save_interval"), "min_prc_duration",
            ],
            "technical": [("offered_config", "confirmed_config"), ("certificate_fingerprint", "public_key_fingerprint")],
        }}

    class Meta(ComputerForm.Meta):
        fields = (
            *ComputerForm.Meta.fields, "hostname", "version", "connection", "configuration", "last_seen", "last_ip",
            "offered_config", "confirmed_config", "pending_commands", "certificate_fingerprint", "public_key_fingerprint",
        )
        labels = {**ComputerForm.Meta.labels, "last_seen": _("Contact"), "last_ip": _("IP address")}
        widgets_readonly = dict.fromkeys(fields, ComputerReadOnlyWidget)

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        computer = self.instance
        self.initial.update(
            connection=computer.get_connection_status().label,
            configuration=computer.get_config_delivery_status().label,
            offered_config=computer.current_config_id,
            confirmed_config=computer.applied_config_id,
            pending_commands=computer.pending_command_count,
        )
