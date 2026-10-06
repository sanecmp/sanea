"""Weekly schedule range model."""

from typing import TYPE_CHECKING, Self

from sanelib.protocol import Range as ClientRange
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models, transaction
from django.db.models import F, Q
from django.utils.translation import gettext_lazy as _

from .base import TimestampedModel
from .identifier_sequence import IdentifierSequence
from .validation import NON_NEGATIVE

if TYPE_CHECKING:
    from ..forms import RangeForm
    from .limits import Limits

class Range(TimestampedModel):
    """One allowed half-open interval contained within a weekday."""

    limits = models.ForeignKey(
        "Limits",
        verbose_name=_("Limits"),
        on_delete=models.CASCADE,
        related_name="ranges",
        help_text=_("Limits set containing this range and its budget."),
    )
    ident = models.PositiveBigIntegerField(
        verbose_name=_("Identifier"),
        validators=[NON_NEGATIVE],
        help_text=_("Stable identifier of this range and its accounting budget."),
    )
    apply = models.BooleanField(
        verbose_name=_("Include in schedule"),
        default=True,
        help_text=_("Include this range in the allowed weekly schedule."),
    )
    weekday = models.PositiveSmallIntegerField(
        verbose_name=_("Weekday"),
        validators=[MinValueValidator(0), MaxValueValidator(6)],
        help_text=_("Weekday from zero for Monday through six for Sunday."),
    )
    since = models.PositiveSmallIntegerField(
        verbose_name=_("Start minute"),
        validators=[MinValueValidator(0), MaxValueValidator(1_439)],
        help_text=_("Range start in minutes since midnight."),
    )
    till = models.PositiveSmallIntegerField(
        verbose_name=_("End minute"),
        validators=[MinValueValidator(1), MaxValueValidator(1_440)],
        help_text=_("Exclusive range end in minutes since midnight."),
    )
    session_rule = models.ForeignKey(
        "SessionRule",
        verbose_name=_("Session rule"),
        on_delete=models.PROTECT,
        related_name="ranges",
        help_text=_("Session and application quotas used by this range."),
    )

    class Meta:
        verbose_name = _("Schedule range")
        verbose_name_plural = _("Schedule ranges")
        ordering = ("limits", "weekday", "since", "pk")
        constraints = [
            models.UniqueConstraint(
                fields=("limits", "ident"),
                name="core_range_limits_ident_unique",
            ),
            models.CheckConstraint(
                condition=Q(weekday__gte=0, weekday__lte=6),
                name="core_range_weekday_valid",
            ),
            models.CheckConstraint(
                condition=Q(since__gte=0, till__lte=1_440) & Q(since__lt=F("till")),
                name="core_range_interval_valid",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.weekday}:{self.since}-{self.till}"

    @classmethod
    @transaction.atomic
    def save_form(cls, form: "RangeForm", limits: "Limits") -> Self:
        """Save a range, forking an assigned snapshot when required."""
        target_limits = limits.checkout_for_edit()
        manager = cls.objects
        source = form.save(commit=False)

        if source.pk and target_limits.pk != limits.pk:
            range_ = manager.get(limits=target_limits, ident=source.ident)
            range_.apply_form(form)

        else:
            range_ = source

        range_.limits = target_limits
        rule_model = cls._meta.get_field("session_rule").remote_field.model
        range_.session_rule = rule_model.objects.get(
            limits=target_limits,
            ident=form.cleaned_data["session_rule"].ident,
        )

        if not range_.pk:
            range_.ident = IdentifierSequence.allocate(cls)

        range_.full_clean()
        range_.save()
        target_limits.materialize_computer_configs()
        return range_

    def build_client_config(self) -> ClientRange:
        """Build this range in the shared sanex configuration format."""
        return ClientRange(
            ident=self.ident,
            apply=self.apply,
            weekday=self.weekday,
            since=self.since,
            till=self.till,
            session_rule_ident=self.session_rule.ident,
        )

    def clean(self) -> None:
        """Validate ownership and prevent overlap of applied ranges."""
        super().clean()
        errors = {}
        limits_id = self.limits_id
        since = self.since
        till = self.till
        pk = self.pk

        if self.session_rule_id and limits_id:

            if self.session_rule.limits_id != limits_id:
                errors["session_rule"] = _(
                    "The session rule must belong to the same limits set."
                )

            elif self.apply and since is not None and till is not None:
                overlaps = type(self).objects.filter(
                    limits_id=limits_id,
                    weekday=self.weekday,
                    apply=True,
                    since__lt=till,
                    till__gt=since,
                )

                if pk:
                    overlaps = overlaps.exclude(pk=pk)

                if overlaps.exists():
                    errors["since"] = _("Applied ranges must not overlap.")

        if errors:
            raise ValidationError(errors)
