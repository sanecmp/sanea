"""Client-command history filter form."""

from django import forms
from django.utils.translation import gettext_lazy as _

from ..models import ClientCommand, CommandStatus, Computer
from .base import SaneaForm


class CommandFilterForm(SaneaForm):
    """Select the computer, type and state shown in command history."""

    STATUS_PENDING = "pending"

    command_computer = forms.ModelChoiceField(
        label=_("Computer"),
        queryset=Computer.objects.none(),
        required=False,
        empty_label=_("All computers"),
    )
    command_type = forms.ChoiceField(
        label=_("Type"),
        required=False,
        choices=(("", _("All command types")),),
    )
    command_status = forms.ChoiceField(
        label=_("Command status"),
        required=False,
        choices=(
            ("", _("All statuses")),
            (STATUS_PENDING, _("Pending")),
            *CommandStatus.choices,
        ),
    )

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        fields = self.fields
        fields["command_computer"].queryset = Computer.objects.all()
        fields["command_type"].choices = (
            ("", _("All command types")),
            *(
                (command_type, command_type)
                for command_type in ClientCommand.get_types()
            ),
        )

    def get_filters(self) -> dict[str, object]:
        """Return validated model-filter values."""

        if not self.is_valid():
            raise ValueError("command filters must be valid")

        cleaned_data = self.cleaned_data
        return {
            "computer": cleaned_data["command_computer"],
            "command_type": cleaned_data["command_type"] or None,
            "status": cleaned_data["command_status"] or None,
        }
