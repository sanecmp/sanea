"""Commands delivered to sanex during synchronization."""

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Self, TYPE_CHECKING

from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import Count, Q, QuerySet
from django.utils.translation import gettext_lazy as _
from sanelib.protocol import Command as ClientCommandMessage

from ...exceptions import ClientRequestError
from .base import TimestampedModel
from .choices import CommandStatus

if TYPE_CHECKING:
    from .computer import Computer

@dataclass(frozen=True, slots=True)
class CommandCounts:
    """Operational totals for pending and failed client commands."""

    pending: int
    failed: int


@dataclass(frozen=True, slots=True)
class CommandRepeatResult:
    """Result of requesting another execution of a failed command."""

    command: "ClientCommand"
    created: bool


class ClientCommand(TimestampedModel):
    """One durable command and its optional terminal result."""

    computer = models.ForeignKey(
        "Computer",
        verbose_name=_("Computer"),
        on_delete=models.CASCADE,
        related_name="commands",
    )
    global_update = models.ForeignKey(
        "GlobalUpdate",
        verbose_name=_("Global update"),
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        editable=False,
        related_name="commands",
    )
    type = models.CharField(
        verbose_name=_("Type"),
        max_length=64,
        help_text=_("Command type understood by sanex."),
    )
    payload = models.JSONField(
        verbose_name=_("Payload"),
        default=dict,
        help_text=_("Command parameters sent to sanex."),
    )
    status = models.CharField(
        verbose_name=_("Result status"),
        max_length=16,
        choices=CommandStatus,
        null=True,
        blank=True,
    )
    error = models.CharField(
        verbose_name=_("Result error"),
        max_length=1_024,
        null=True,
        blank=True,
    )
    completed = models.DateTimeField(
        verbose_name=_("Completed"),
        null=True,
        blank=True,
    )

    class Meta:
        verbose_name = _("Client command")
        verbose_name_plural = _("Client commands")
        ordering = ("computer", "pk")
        constraints = (
            models.UniqueConstraint(
                fields=("global_update", "computer"),
                condition=Q(status__isnull=True),
                name="one_pending_global_update_per_computer",
            ),
        )

    def __str__(self) -> str:
        return f"{self.computer_id} #{self.pk}: {self.type}"

    @classmethod
    def count_operational_statuses(cls) -> CommandCounts:
        """Count commands that are pending or have failed."""
        counts = cls.objects.aggregate(
            pending=Count("pk", filter=Q(status__isnull=True)),
            failed=Count("pk", filter=Q(status=CommandStatus.FAILED)),
        )
        return CommandCounts(**counts)

    @classmethod
    def get_types(cls) -> tuple[str, ...]:
        """Return command types currently present in history."""
        return tuple(
            cls.objects.order_by("type").values_list("type", flat=True).distinct()
        )

    @classmethod
    def get_recent(
        cls,
        *,
        computer: "Computer | None"=None,
        status: str | None = None,
        command_type: str | None = None,
    ) -> models.QuerySet[Self]:
        """Return commands matching optional filters, newest first."""
        commands = cls.objects.select_related("computer")

        if computer is not None:
            commands = commands.filter(computer=computer)

        if status == "pending":
            commands = commands.filter(status__isnull=True)

        elif status is not None:
            commands = commands.filter(status=status)

        if command_type is not None:
            commands = commands.filter(type=command_type)

        return commands.order_by("-created", "-pk")

    @transaction.atomic
    def repeat(self) -> CommandRepeatResult:
        """Queue the same failed command unless an identical one is pending."""
        commands = type(self).objects
        source = commands.select_for_update().get(pk=self.pk)

        if source.status != CommandStatus.FAILED:
            raise ValidationError(_("Only failed commands can be repeated."))

        computer = source.computer
        command_type = source.type
        payload = source.payload
        pending = commands.filter(
            computer=computer,
            type=command_type,
            payload=payload,
            status__isnull=True,
        ).first()

        if pending is not None:
            return CommandRepeatResult(command=pending, created=False)

        repeated = commands.create(
            computer=computer,
            type=command_type,
            payload=payload,
        )
        return CommandRepeatResult(command=repeated, created=True)

    def format_payload(self) -> str:
        """Format command parameters for compact human-readable display."""
        payload = self.payload

        if not payload:
            return ""

        if self.type == "update":
            version = payload.get("version")
            index_url = payload.get("index_url")

            if version and index_url:
                return f"{version} · {index_url}"

        return json.dumps(payload, ensure_ascii=False, sort_keys=True)

    def format_payload_details(self) -> str:
        """Format the complete command payload for detailed display."""
        return json.dumps(self.payload, ensure_ascii=False, indent=2, sort_keys=True)

    def build_client_command(self) -> ClientCommandMessage:
        """Build this pending command in the shared wire format."""
        return ClientCommandMessage(
            ident=self.pk,
            type=self.type,
            payload=self.payload,
        )

    def apply_result(self, status: CommandStatus, error: str | None, completed: datetime) -> None:
        """Idempotently apply one terminal result reported by sanex."""
        current_status = self.status
        current_error = self.error

        if current_status:

            if current_status != status or current_error != error:
                raise ClientRequestError(
                    f"Command {self.pk} already has another result"
                )

            return

        setattr(self, "status", status)
        setattr(self, "error", error)
        self.completed = completed
        self.full_clean()
        self.save(update_fields=("status", "error", "completed", "updated"))

    def clean(self) -> None:
        """Require an object payload and a consistent terminal result."""
        super().clean()
        errors = {}

        if not isinstance(self.payload, dict):
            errors["payload"] = _("Command payload must be an object.")

        status = self.status
        completed = self.completed

        if status and completed is None:
            errors["completed"] = _("A completed command requires completion time.")

        if not status and (self.error is not None or completed is not None):
            errors["status"] = _("Result details require a terminal status.")

        if errors:
            raise ValidationError(errors)
