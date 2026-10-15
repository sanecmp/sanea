"""Session quota rule model."""

from typing import TYPE_CHECKING, Self

from sanelib.protocol import SessionRule as ClientSessionRule
from django.db import models
from django.utils.translation import gettext_lazy as _

from .base import TimestampedModel
from .rule_editing import save_limits_form
from .validation import NON_NEGATIVE

if TYPE_CHECKING:
    from ..forms import SessionRuleForm
    from .limits import Limits

class SessionRule(TimestampedModel):
    """Session quotas reusable by several ranges in one limits set."""

    limits = models.ForeignKey(
        "Limits",
        verbose_name=_("Limits"),
        on_delete=models.CASCADE,
        related_name="session_rules",
        help_text=_("Limits set containing this rule."),
    )
    ident = models.PositiveBigIntegerField(
        verbose_name=_("Identifier"),
        validators=[NON_NEGATIVE],
        help_text=_("Stable identifier preserved when the rule is copied."),
    )
    name = models.CharField(
        verbose_name=_("Name"),
        max_length=160,
        help_text=_("Parent-facing rule name; it does not affect accounting identity."),
    )
    apply = models.BooleanField(
        verbose_name=_("Apply limits"),
        default=True,
        help_text=_("Apply session quotas and nested application rules."),
    )
    max_sessions = models.PositiveIntegerField(
        verbose_name=_("Maximum sessions"),
        null=True,
        blank=True,
        validators=[NON_NEGATIVE],
        help_text=_("Maximum sessions in one range occurrence; empty means unlimited."),
    )
    max_duration = models.PositiveIntegerField(
        verbose_name=_("Maximum duration"),
        null=True,
        blank=True,
        validators=[NON_NEGATIVE],
        help_text=_(
            "Maximum duration of one session in seconds; empty means unlimited."
        ),
    )
    break_duration = models.PositiveIntegerField(
        verbose_name=_("Break duration"),
        default=7_200,
        validators=[NON_NEGATIVE],
        help_text=_("Required break duration in seconds; zero disables the break."),
    )

    class Meta:
        verbose_name = _("Session rule")
        verbose_name_plural = _("Session rules")
        ordering = ("limits", "name", "pk")
        constraints = [
            models.UniqueConstraint(
                fields=("limits", "ident"),
                name="core_session_rule_limits_ident_unique",
            ),
        ]

    def __str__(self) -> str:
        return self.name

    @classmethod
    def save_form(cls, form: "SessionRuleForm", limits: "Limits") -> Self:
        """Save a rule, forking an assigned snapshot when required."""
        return save_limits_form(cls, form, limits, get_relations=lambda target: {"limits": target})

    def build_client_config(self) -> ClientSessionRule:
        """Build this rule in the shared sanex configuration format."""
        app_rules = sorted(
            self.app_rules.all(),
            key=lambda item: (item.ident, item.pk),
        )
        return ClientSessionRule(
            ident=self.ident,
            apply=self.apply,
            max_sessions=self.max_sessions,
            max_duration=self.max_duration,
            break_duration=self.break_duration,
            app_rules=tuple(rule.build_client_config() for rule in app_rules),
        )
