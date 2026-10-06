"""Named pointer to the current immutable limits snapshot."""

from typing import Self, TYPE_CHECKING

from django.db import models, transaction
from django.utils.translation import gettext_lazy as _

from .base import TimestampedModel
from .limits import Limits

if TYPE_CHECKING:
    from ..forms import LimitsTemplateForm

class LimitsTemplate(TimestampedModel):
    """A named template whose current snapshot can advance independently."""

    name = models.CharField(
        verbose_name=_("Name"),
        max_length=160,
        help_text=_("Parent-facing template name."),
    )
    current_limits = models.OneToOneField(
        Limits,
        verbose_name=_("Current limits snapshot"),
        on_delete=models.PROTECT,
        related_name="current_for_template",
        help_text=_("Current immutable configuration snapshot for this template."),
    )

    class Meta:
        verbose_name = _("Limits template")
        verbose_name_plural = _("Limits templates")
        ordering = ("name", "pk")

    def __str__(self) -> str:
        return self.name

    @classmethod
    @transaction.atomic
    def save_form(cls, form: "LimitsTemplateForm") -> Self:
        """Create a template with a snapshot or rename an existing template."""
        save_form = form.save

        if form.instance.pk:
            return save_form()

        snapshot = Limits.objects.create(name=form.cleaned_data["name"])
        template = save_form(commit=False)
        template.current_limits = snapshot
        template.full_clean()
        template.save()
        return template
