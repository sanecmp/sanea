"""Abstract base models shared by the sanea domain."""

from django.db import models
from django.utils.translation import gettext_lazy as _
from django.forms import ModelForm


class TimestampedModel(models.Model):
    """Add automatically maintained creation and modification timestamps."""

    created = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_("Created"),
    )
    updated = models.DateTimeField(
        auto_now=True,
        verbose_name=_("Updated"),
    )

    def get_editable_values(self, *excluded: str) -> dict[str, object]:
        """Return editable concrete field values suitable for cloning."""
        values = {}

        for field in self._meta.concrete_fields:
            field_name = field.name

            if field.editable and not field.primary_key and field_name not in excluded:
                values[field_name] = getattr(self, field_name)

        return values

    def apply_form(self, form: ModelForm) -> None:
        """Apply the fields declared by a validated model form."""

        for field_name in form._meta.fields:
            setattr(self, field_name, form.cleaned_data[field_name])

    class Meta:
        abstract = True
