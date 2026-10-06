"""Registered-computer list filter form."""

from django import forms
from django.utils.translation import gettext_lazy as _

from ..models import ComputerStatus, ConfigDeliveryStatus, ConnectionStatus
from .base import SaneaForm


class ComputerFilterForm(SaneaForm):
    """Select access, connection and configuration states for the computer list."""

    access = forms.ChoiceField(
        label=_("Access"),
        required=False,
        choices=(("", _("All access states")), *ComputerStatus.choices),
    )
    connection = forms.ChoiceField(
        label=_("Connection"),
        required=False,
        choices=(("", _("All connection states")), *ConnectionStatus.choices),
    )
    config_delivery = forms.ChoiceField(
        label=_("Configuration"),
        required=False,
        choices=(("", _("All configuration states")), *ConfigDeliveryStatus.choices),
    )

    def get_filters(self) -> dict[str, str | None]:
        """Return validated model-filter values."""

        if not self.is_valid():
            raise ValueError("computer filters must be valid")

        cleaned_data = self.cleaned_data
        return {
            "access": cleaned_data["access"] or None,
            "connection": cleaned_data["connection"] or None,
            "config_delivery": cleaned_data["config_delivery"] or None,
        }
