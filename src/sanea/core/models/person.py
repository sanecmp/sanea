"""Person model."""

from collections.abc import Iterable
from typing import TYPE_CHECKING

from django.db import models, transaction
from django.utils.translation import gettext_lazy as _

from ...exceptions import LimitsTemplateError
from .base import TimestampedModel
from .limits_template import LimitsTemplate

if TYPE_CHECKING:
    from .account import Account

class Person(TimestampedModel):
    """A person whose local operating-system accounts can span computers."""

    name = models.CharField(
        verbose_name=_("Name"),
        max_length=160,
        help_text=_("Name shown to the parent in the browser interface."),
    )
    limits_tpl = models.ForeignKey(
        LimitsTemplate,
        verbose_name=_("Limits template"),
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="people",
        help_text=_(
            "Template available for explicit assignment to this person's accounts."
        ),
    )

    class Meta:
        verbose_name = _("Person")
        verbose_name_plural = _("People")
        ordering = ("name", "pk")

    def __str__(self) -> str:
        return self.name

    @transaction.atomic
    def propagate_template(self, accounts: Iterable["Account"]) -> int:
        """Assign the current template snapshot to selected accounts."""
        person = (
            type(self)
            .objects.select_for_update()
            .select_related("limits_tpl__current_limits")
            .get(pk=self.pk)
        )

        if not person.limits_tpl_id:
            raise LimitsTemplateError(
                "A person without a template cannot be propagated"
            )

        account_ids = [account.pk for account in accounts]
        selected = person.accounts.select_for_update().filter(pk__in=account_ids)
        computer_ids = set()
        count = 0

        for account in selected:
            account.limits = person.limits_tpl.current_limits
            account.save(update_fields=("limits", "updated"))
            computer_ids.add(account.computer_id)
            count += 1

        computer_model = self._meta.apps.get_model("core", "Computer")
        computer_model.materialize_configs(computer_ids)
        return count
