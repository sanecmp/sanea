"""Global sanex update command form."""

from django import forms
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from pydantic import ValidationError as PydanticValidationError
from sanelib.protocol import UpdateCommandPayload

from .base import SaneaForm


class SanexUpdateForm(SaneaForm):
    """Validate a release and package index for all allowed computers."""

    version = forms.CharField(
        label=_("Target version"),
        max_length=64,
        help_text=_("PEP 440 version of the sanex package to install."),
    )
    index_url = forms.URLField(
        label=_("Package index URL"),
        max_length=2_048,
        initial="https://pypi.org/simple",
        help_text=_("Absolute HTTPS URL of the Python package index."),
    )

    def clean(self) -> dict[str, object]:
        """Validate form values against the shared command payload schema."""
        cleaned_data = super().clean()

        if self.errors:
            return cleaned_data

        try:
            UpdateCommandPayload.model_validate(cleaned_data)

        except PydanticValidationError as error:

            for detail in error.errors(include_url=False):
                location = detail["loc"]
                field = location[0] if location else None
                messages = {
                    "version": _("Enter a version conforming to PEP 440."),
                    "index_url": _(
                        "Enter an absolute HTTPS URL without credentials or a fragment."
                    ),
                }
                message = messages.get(field, _("Invalid update parameters."))
                self.add_error(
                    field if field in self.fields else None,
                    ValidationError(message),
                )

        return cleaned_data

    def get_payload(self) -> UpdateCommandPayload:
        """Build the shared payload after successful form validation."""

        if not self.is_valid():
            raise ValueError("sanex update form must be valid")

        return UpdateCommandPayload.model_validate(self.cleaned_data)
