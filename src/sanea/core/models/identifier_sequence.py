"""Persistent allocation of accounting identifiers across snapshot branches."""

from django.db import models, transaction
from django.db.models import Max
from django.utils.translation import gettext_lazy as _


class IdentifierSequence(models.Model):
    """Keep one never-decreasing identifier sequence for each budget kind."""

    RANGE = "range"
    SESSION_RULE = "session_rule"
    APP_RULE = "app_rule"
    MODEL_KINDS = {
        "core.range": RANGE,
        "core.sessionrule": SESSION_RULE,
        "core.apprule": APP_RULE,
    }

    kind = models.CharField(
        verbose_name=_("Kind"),
        max_length=32,
        primary_key=True,
        choices=(
            (RANGE, _("Schedule range")),
            (SESSION_RULE, _("Session rule")),
            (APP_RULE, _("Application rule")),
        ),
    )
    next_ident = models.PositiveBigIntegerField(
        verbose_name=_("Next identifier"),
        default=0,
    )

    class Meta:
        verbose_name = _("Identifier sequence")
        verbose_name_plural = _("Identifier sequences")

    def __str__(self) -> str:
        return f"{self.kind}: {self.next_ident}"

    @classmethod
    @transaction.atomic
    def allocate(cls, model: type[models.Model]) -> int:
        """Reserve an identifier above both the sequence and existing rows."""
        label = model._meta.label_lower
        kind = cls.MODEL_KINDS.get(label)

        if kind is None:
            raise ValueError(f"unsupported identifier model: {label}")

        sequence, _ = cls.objects.select_for_update().get_or_create(kind=kind)
        maximum = model.objects.aggregate(value=Max("ident"))["value"]
        existing_next = 0 if maximum is None else maximum + 1
        ident = max(sequence.next_ident, existing_next)
        sequence.next_ident = ident + 1
        sequence.save(update_fields=("next_ident",))
        return ident
