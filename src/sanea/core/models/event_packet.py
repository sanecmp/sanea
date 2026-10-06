"""Received immutable sanex event packet model."""

from django.db import models
from django.db.models import F, Q
from django.utils.translation import gettext_lazy as _

from .base import TimestampedModel
from .validation import FINGERPRINT


class EventPacket(TimestampedModel):
    """Identity and bounds of one validated event packet."""

    account = models.ForeignKey(
        "Account",
        verbose_name=_("Account"),
        on_delete=models.CASCADE,
        related_name="event_packets",
        help_text=_("Local account whose events were received."),
    )
    sha256 = models.CharField(
        verbose_name=_("SHA-256"),
        max_length=64,
        validators=[FINGERPRINT],
        help_text=_("SHA-256 of the exact received JSONL bytes."),
    )
    first_seq = models.PositiveBigIntegerField(
        verbose_name=_("First sequence"),
        help_text=_("Sequence number of the first event in this packet."),
    )
    last_seq = models.PositiveBigIntegerField(
        verbose_name=_("Last sequence"),
        help_text=_("Sequence number of the last event in this packet."),
    )
    event_count = models.PositiveIntegerField(
        verbose_name=_("Event count"),
        help_text=_("Number of events stored from this packet."),
    )
    byte_size = models.PositiveIntegerField(
        verbose_name=_("Byte size"),
        help_text=_("Size of the exact received JSONL body in bytes."),
    )

    class Meta:
        verbose_name = _("Event packet")
        verbose_name_plural = _("Event packets")
        ordering = ("account", "first_seq", "pk")
        constraints = [
            models.UniqueConstraint(
                fields=("account", "sha256"),
                name="core_eventpacket_account_sha_unique",
            ),
            models.CheckConstraint(
                condition=Q(first_seq__lte=F("last_seq")),
                name="core_eventpacket_sequence_range_valid",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.account_id} {self.first_seq}-{self.last_seq}"
