"""Limits set model."""

from typing import Self, TYPE_CHECKING

from sanelib.protocol import Limits as ClientLimits
from django.db import models, transaction
from django.utils.translation import gettext_lazy as _

from ...exceptions import LimitsTemplateError
from .app_rule import AppRule
from .base import TimestampedModel
from .range import Range
from .session_rule import SessionRule

if TYPE_CHECKING:
    from .computer_config import ComputerConfig

class Limits(TimestampedModel):
    """An immutable-ready weekly configuration snapshot and its rules."""

    name = models.CharField(
        verbose_name=_("Name"),
        max_length=160,
        help_text=_("Name of this configuration snapshot or independent set."),
    )

    class Meta:
        verbose_name = _("Limits set")
        verbose_name_plural = _("Limits sets")
        ordering = ("name", "pk")

    def __str__(self) -> str:
        return self.name

    @classmethod
    def delete_unreferenced(cls) -> int:
        """Delete snapshots unused by accounts and template pointers."""
        snapshots = cls.objects.filter(
            accounts__isnull=True,
            current_for_template__isnull=True,
        )
        count = snapshots.count()
        Range.objects.filter(limits__in=snapshots).delete()
        snapshots.delete()
        return count

    def materialize_computer_configs(self) -> tuple["ComputerConfig", ...]:
        """Materialize configs for computers using this limits snapshot."""
        computer_model = self._meta.apps.get_model("core", "Computer")
        computer_ids = self.accounts.values_list("computer_id", flat=True).distinct()
        return computer_model.materialize_configs(computer_ids)

    def build_client_config(self) -> ClientLimits:
        """Build this limits graph in the shared sanex configuration format."""
        ranges = sorted(
            self.ranges.all(),
            key=lambda item: (
                item.weekday,
                item.since,
                item.ident,
                item.pk,
            ),
        )
        session_rules = sorted(
            self.session_rules.all(),
            key=lambda rule: (rule.ident, rule.pk),
        )
        return ClientLimits(
            ranges=tuple(range_.build_client_config() for range_ in ranges),
            session_rules=tuple(rule.build_client_config() for rule in session_rules),
        )

    @transaction.atomic
    def clone(self, name: str | None = None) -> Self:
        """Create an independent deep copy preserving stable identifiers."""
        source = type(self).objects.select_for_update().get(pk=self.pk)
        return source._copy(name or source.name)

    def _copy(self, name: str) -> Self:

        target = type(self).objects.create(name=name)
        rule_map = {}

        for source_rule in self.session_rules.prefetch_related("app_rules"):
            target_rule = SessionRule(
                limits=target,
                **source_rule.get_editable_values("limits"),
            )
            target_rule.full_clean()
            target_rule.save()
            rule_map[source_rule.pk] = target_rule

            for source_app_rule in source_rule.app_rules.all():
                target_app_rule = AppRule(
                    session_rule=target_rule,
                    **source_app_rule.get_editable_values("session_rule"),
                )
                target_app_rule.full_clean()
                target_app_rule.save()

        for source_range in self.ranges.select_related("session_rule"):
            target_range = Range(
                limits=target,
                session_rule=rule_map[source_range.session_rule_id],
                **source_range.get_editable_values("limits", "session_rule"),
            )
            target_range.full_clean()
            target_range.save()

        return target

    @transaction.atomic
    def checkout_for_edit(self) -> Self:
        """Fork an assigned snapshot before modifying its graph."""

        limits = type(self).objects.select_for_update().get(pk=self.pk)
        template_model = self._meta.apps.get_model("core", "LimitsTemplate")
        template = (
            template_model.objects.select_for_update()
            .filter(current_limits=limits)
            .first()
        )
        accounts = limits.accounts

        if template:

            if not accounts.exists():
                return limits

            target = limits._copy(template.name)
            template.current_limits = target
            template.save(update_fields=("current_limits", "updated"))
            return target

        if accounts.count() > 1:
            raise LimitsTemplateError(
                "A shared account snapshot must be customized through a selected account"
            )

        return limits
