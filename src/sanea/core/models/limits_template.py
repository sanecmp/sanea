"""Named pointer to the current immutable limits snapshot."""

from collections.abc import Iterable
from typing import Self, TYPE_CHECKING

from django.db import models, transaction
from django.utils.translation import gettext_lazy as _
from django.utils.timezone import now

from .base import TimestampedModel
from .limits import Limits

if TYPE_CHECKING:
    from ..forms import LimitsTemplateForm
    from .account import Account

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
        """Save a template and its default recipients without changing account limits."""
        save_form = form.save

        if form.instance.pk:
            template = save_form()

        else:
            snapshot = Limits.objects.create(name=form.cleaned_data["name"])
            template = save_form(commit=False)
            template.current_limits = snapshot
            template.full_clean()
            template.save()

        people = form.cleaned_data["people"]
        timestamp = now()
        template.people.exclude(pk__in=people).update(limits_tpl=None, updated=timestamp)
        people.exclude(limits_tpl=template).update(limits_tpl=template, updated=timestamp)
        return template

    @transaction.atomic
    def apply_to_accounts(self, accounts: Iterable["Account"]) -> int:
        """Apply the latest template version to selected recipients' accounts."""
        template = type(self).objects.select_for_update().select_related("current_limits").get(pk=self.pk)
        account_ids = [account.pk for account in accounts]
        account_model = self._meta.apps.get_model("core", "Account")
        selected = account_model.objects.select_for_update().filter(pk__in=account_ids, person__limits_tpl=template)
        computer_ids = set()
        count = 0

        for account in selected:
            account.limits = template.current_limits
            account.save(update_fields=("limits", "updated"))
            computer_ids.add(account.computer_id)
            count += 1

        computer_model = self._meta.apps.get_model("core", "Computer")
        computer_model.materialize_configs(computer_ids)
        return count
