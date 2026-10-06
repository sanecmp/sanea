"""One active sanex update campaign shared by all allowed computers."""

from dataclasses import dataclass
from typing import Self

from django.db import models, transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from sanelib.protocol import UpdateCommandPayload

from .base import TimestampedModel
from .choices import ComputerStatus
from .client_command import ClientCommand
from .computer import Computer


@dataclass(frozen=True, slots=True)
class UpdateActivationResult:
    """Result of activating one global sanex update campaign."""

    update: "GlobalUpdate"
    created: int


class GlobalUpdate(TimestampedModel):
    """A sanex version offered to every allowed computer until cancellation."""

    version = models.CharField(
        verbose_name=_("Target version"),
        max_length=64,
        help_text=_("Exact sanex package version to install."),
    )
    index_url = models.URLField(
        verbose_name=_("Package index URL"),
        max_length=2_048,
        help_text=_("Python package index used to install the target version."),
    )
    active = models.BooleanField(
        verbose_name=_("Active"),
        default=True,
        editable=False,
    )
    cancelled = models.DateTimeField(
        verbose_name=_("Cancelled"),
        null=True,
        blank=True,
        editable=False,
    )

    class Meta:
        verbose_name = _("Global sanex update")
        verbose_name_plural = _("Global sanex updates")
        ordering = ("-created", "-pk")
        constraints = (
            models.UniqueConstraint(
                fields=("active",),
                condition=Q(active=True),
                name="one_active_global_update",
            ),
        )

    def __str__(self) -> str:
        return f"sanex {self.version}"

    @classmethod
    def get_active(cls) -> Self | None:
        """Return the active update campaign, if any."""
        return cls.objects.filter(active=True).first()

    @classmethod
    @transaction.atomic
    def activate(cls, payload: UpdateCommandPayload) -> UpdateActivationResult:
        """Replace the active campaign and queue it for every allowed computer."""
        active_updates = cls.objects.select_for_update().filter(active=True)
        now = timezone.now()
        ClientCommand.objects.filter(
            global_update__in=active_updates,
            status__isnull=True,
        ).delete()
        active_updates.update(active=False, cancelled=now, updated=now)

        update = cls.objects.create(
            version=payload.version,
            index_url=f"{payload.index_url}",
        )
        computers = tuple(
            Computer.objects.select_for_update()
            .filter(status=ComputerStatus.ALLOWED)
            .exclude(version=update.version)
            .order_by("pk")
        )
        commands = [update.build_command(computer) for computer in computers]
        ClientCommand.objects.bulk_create(commands)
        return UpdateActivationResult(update=update, created=len(commands))

    @transaction.atomic
    def cancel(self) -> int:
        """Cancel this campaign and remove its commands awaiting execution."""
        update = type(self).objects.select_for_update().get(pk=self.pk)

        if not update.active:
            return 0

        deleted, _ = update.commands.filter(status__isnull=True).delete()
        update.active = False
        update.cancelled = timezone.now()
        update.save(update_fields=("active", "cancelled", "updated"))
        self.active = update.active
        self.cancelled = update.cancelled
        return deleted

    def ensure_command(self, computer: Computer) -> ClientCommand | None:
        """Ensure an allowed computer has this campaign's durable command."""

        if not self.active or computer.status != ComputerStatus.ALLOWED:
            return None

        commands = self.commands
        pending = commands.filter(computer=computer, status__isnull=True).first()

        if pending is not None:
            return pending

        if computer.version == self.version:
            return None

        return commands.create(
            computer=computer,
            type="update",
            payload=self.get_payload(),
        )

    def build_command(self, computer: Computer) -> ClientCommand:
        """Build an unsaved client command for this campaign and computer."""
        return ClientCommand(
            computer=computer,
            global_update=self,
            type="update",
            payload=self.get_payload(),
        )

    def get_payload(self) -> dict[str, str]:
        """Return the validated wire payload represented by this campaign."""
        return UpdateCommandPayload(
            version=self.version,
            index_url=self.index_url,
        ).model_dump(mode="json")
