"""Application quota and recognition rule model."""

import re
from typing import TYPE_CHECKING, Self

from sanelib.protocol import AppRule as ClientAppRule, MatchType as ClientMatchType
from django.core.exceptions import NON_FIELD_ERRORS, ValidationError
from django.db import models, transaction
from django.utils.translation import gettext_lazy as _

from .base import TimestampedModel
from .choices import MatchType
from .identifier_sequence import IdentifierSequence
from .validation import NON_NEGATIVE

if TYPE_CHECKING:
    from ..forms import AppRuleForm
    from .session_rule import SessionRule

class AppRule(TimestampedModel):
    """Application quotas and window recognition conditions."""

    session_rule = models.ForeignKey(
        "SessionRule",
        verbose_name=_("Session rule"),
        on_delete=models.CASCADE,
        related_name="app_rules",
        help_text=_("Session rule containing this application rule."),
    )
    ident = models.PositiveBigIntegerField(
        verbose_name=_("Identifier"),
        validators=[NON_NEGATIVE],
        help_text=_("Stable identifier of this application's accounting budget."),
    )
    name = models.CharField(
        verbose_name=_("Name"),
        max_length=160,
        help_text=_(
            "Parent-facing application name; it is not a recognition condition."
        ),
    )
    apply = models.BooleanField(
        verbose_name=_("Apply limits"),
        default=True,
        help_text=_("Apply this application rule."),
    )
    max_launches = models.PositiveIntegerField(
        verbose_name=_("Maximum launches"),
        null=True,
        blank=True,
        validators=[NON_NEGATIVE],
        help_text=_("Maximum launches in one range occurrence; empty means unlimited."),
    )
    max_time = models.PositiveIntegerField(
        verbose_name=_("Maximum time"),
        null=True,
        blank=True,
        validators=[NON_NEGATIVE],
        help_text=_("Maximum total usage time in seconds; empty means unlimited."),
    )
    prc_name = models.CharField(
        verbose_name=_("Process name"),
        max_length=256,
        null=True,
        blank=True,
        help_text=_("Optional process-name recognition condition."),
    )
    prc_name_match = models.CharField(
        verbose_name=_("Process name match"),
        max_length=16,
        choices=MatchType,
        null=True,
        blank=True,
        help_text=_("Matching method for prc_name."),
    )
    exe = models.CharField(
        verbose_name=_("Executable"),
        max_length=4_096,
        null=True,
        blank=True,
        help_text=_("Optional resolved executable-path recognition condition."),
    )
    exe_match = models.CharField(
        verbose_name=_("Executable match"),
        max_length=16,
        choices=MatchType,
        null=True,
        blank=True,
        help_text=_("Matching method for exe."),
    )
    wnd_title = models.CharField(
        verbose_name=_("Window title"),
        max_length=512,
        null=True,
        blank=True,
        help_text=_("Optional current window-title recognition condition."),
    )
    wnd_title_match = models.CharField(
        verbose_name=_("Window title match"),
        max_length=16,
        choices=MatchType,
        null=True,
        blank=True,
        help_text=_("Matching method for wnd_title."),
    )

    class Meta:
        verbose_name = _("Application rule")
        verbose_name_plural = _("Application rules")
        ordering = ("session_rule", "name", "pk")
        constraints = [
            models.UniqueConstraint(
                fields=("session_rule", "ident"),
                name="core_app_rule_session_ident_unique",
            ),
        ]

    def __str__(self) -> str:
        return self.name

    @classmethod
    @transaction.atomic
    def save_form(cls, form: "AppRuleForm", session_rule: "SessionRule") -> Self:
        """Save a rule, forking an assigned snapshot when required."""
        target_limits = session_rule.limits.checkout_for_edit()
        manager = cls.objects
        session_rule_model = cls._meta.get_field("session_rule").remote_field.model
        target_rule = session_rule_model.objects.get(
            limits=target_limits,
            ident=session_rule.ident,
        )
        source = form.save(commit=False)

        if source.pk and target_limits.pk != session_rule.limits_id:
            rule = manager.get(
                session_rule__limits=target_limits,
                ident=source.ident,
            )
            rule.apply_form(form)

        else:
            rule = source

        rule.session_rule = target_rule

        if not rule.pk:
            rule.ident = IdentifierSequence.allocate(cls)

        rule.full_clean()
        rule.save()
        target_limits.materialize_computer_configs()
        return rule

    def build_client_config(self) -> ClientAppRule:
        """Build this rule in the shared sanex configuration format."""
        return ClientAppRule(
            ident=self.ident,
            name=self.name,
            apply=self.apply,
            max_launches=self.max_launches,
            max_time=self.max_time,
            prc_name=self.prc_name,
            prc_name_match=(
                ClientMatchType(self.prc_name_match)
                if self.prc_name_match is not None
                else None
            ),
            exe=self.exe,
            exe_match=(
                ClientMatchType(self.exe_match) if self.exe_match is not None else None
            ),
            wnd_title=self.wnd_title,
            wnd_title_match=(
                ClientMatchType(self.wnd_title_match)
                if self.wnd_title_match is not None
                else None
            ),
        )

    def clean(self) -> None:
        """Validate limits, recognition pairs, regexes and stable identity."""
        super().clean()
        errors = {}
        general_errors = []
        add_general_error = general_errors.append

        if self.max_launches is None and self.max_time is None:
            add_general_error(
                _("Set at least one of maximum launches or maximum time.")
            )

        conditions = (
            ("prc_name", self.prc_name, self.prc_name_match),
            ("exe", self.exe, self.exe_match),
            ("wnd_title", self.wnd_title, self.wnd_title_match),
        )

        if not any(value for _, value, _ in conditions):
            add_general_error(_("Set at least one application recognition condition."))

        for name, value, match_type in conditions:

            if value and not match_type:
                errors[f"{name}_match"] = _("A matching method is required.")

            elif not value and match_type:
                errors[f"{name}_match"] = _("A matching method requires its condition.")

            elif value and match_type == MatchType.REGEX:
                try:
                    re.compile(value)

                except re.error as error:
                    errors[name] = ValidationError(
                        _("Invalid regular expression: %(error)s"),
                        params={"error": error},
                    )

        if general_errors:
            errors[NON_FIELD_ERRORS] = general_errors

        ident = self.ident
        pk = self.pk

        if self.session_rule_id and ident is not None:
            duplicates = type(self).objects.filter(
                session_rule__limits_id=self.session_rule.limits_id,
                ident=ident,
            )

            if pk:
                duplicates = duplicates.exclude(pk=pk)

            if duplicates.exists():
                errors["ident"] = _(
                    "AppRule ident must be unique within one limits set."
                )

        if errors:
            raise ValidationError(errors)
