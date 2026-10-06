"""Local operating-system account model."""

from typing import Self, TYPE_CHECKING

from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.utils.translation import gettext_lazy as _
from sanelib.protocol import Account as ClientAccount, ParsedEventPacket

from ...exceptions import ClientAccessError, EventSequenceConflictError
from .activity_event import ActivityEvent
from .base import TimestampedModel
from .event_packet import EventPacket
from .limits import Limits
from .limits_template import LimitsTemplate
from .person import Person
from .validation import NON_NEGATIVE

if TYPE_CHECKING:
    from ..forms import AccountForm

class Account(TimestampedModel):
    """A local account identified by UID on one computer."""

    computer = models.ForeignKey(
        "Computer",
        verbose_name=_("Computer"),
        on_delete=models.CASCADE,
        related_name="accounts",
        help_text=_("Computer on which this local account exists."),
    )
    uid = models.PositiveBigIntegerField(
        verbose_name=_("UID"),
        validators=[NON_NEGATIVE],
        help_text=_("Local account UID used by logind and process accounting."),
    )
    login = models.CharField(
        verbose_name=_("Login"),
        max_length=256,
        help_text=_("Login most recently reported by sanex."),
    )
    name = models.CharField(
        verbose_name=_("Display name"),
        max_length=256,
        help_text=_("Display name most recently reported by sanex."),
    )
    present = models.BooleanField(
        verbose_name=_("Present"),
        default=True,
        help_text=_("Whether the account is present in the latest complete snapshot."),
    )
    person = models.ForeignKey(
        Person,
        verbose_name=_("Person"),
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="accounts",
        help_text=_("Optional person to whom this concrete local account belongs."),
    )
    limits = models.ForeignKey(
        Limits,
        verbose_name=_("Limits"),
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="accounts",
        help_text=_("Immutable limits snapshot currently assigned to this account."),
    )
    collect = models.BooleanField(
        verbose_name=_("Collect events"),
        default=False,
        help_text=_("Collect session and process events for this account."),
    )
    apply = models.BooleanField(
        verbose_name=_("Apply limits"),
        default=False,
        help_text=_("Apply the account schedule and quota restrictions."),
    )

    class Meta:
        verbose_name = _("Account")
        verbose_name_plural = _("Accounts")
        ordering = ("computer", "uid")
        constraints = [
            models.UniqueConstraint(
                fields=("computer", "uid"),
                name="core_account_computer_uid_unique",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.login} ({self.uid}@{self.computer_id})"

    def update_report(self, login: str, name: str) -> None:
        """Apply mutable identity fields from one sanex account report."""
        changed_fields = []
        add_changed_field = changed_fields.append

        for field_name, value in (("login", login), ("name", name)):

            if getattr(self, field_name) != value:
                setattr(self, field_name, value)
                add_changed_field(field_name)

        is_present = self.present

        if not is_present:
            setattr(self, "present", True)
            add_changed_field("present")

        if changed_fields:
            self.save(update_fields=(*changed_fields, "updated"))

    @transaction.atomic
    def create_limits(self, name: str) -> Limits:
        """Create and attach an empty limits set unless one already exists."""
        account = (
            type(self)
            .objects.select_for_update()
            .select_related("limits")
            .get(pk=self.pk)
        )
        limits = account.limits

        if limits is not None:
            return limits

        limits = Limits.objects.create(name=name)
        setattr(account, "limits", limits)
        account.save(update_fields=("limits", "updated"))
        account.computer.materialize_config()
        return limits

    @transaction.atomic
    def customize_limits(self) -> Limits:
        """Ensure this account has an independently editable snapshot."""
        account = (
            type(self)
            .objects.select_for_update()
            .select_related("computer", "limits")
            .get(pk=self.pk)
        )
        name = f"{account.login} @ {account.computer.hostname}"
        limits = account.limits

        if limits is None:
            return account.create_limits(name)

        shared = limits.accounts.exclude(pk=account.pk).exists()
        template_snapshot = LimitsTemplate.objects.filter(
            current_limits=limits
        ).exists()

        if not shared and not template_snapshot:
            return limits

        target = limits._copy(name)
        setattr(account, "limits", target)
        account.save(update_fields=("limits", "updated"))
        account.computer.materialize_config()
        return target

    @classmethod
    @transaction.atomic
    def save_form(cls, form: "AccountForm") -> Self:
        """Save settings and assign a newly selected person's snapshot."""
        previous_person_id = (
            cls.objects.select_for_update()
            .only("person_id")
            .get(pk=form.instance.pk)
            .person_id
        )
        account = form.save()
        person_id = account.person_id

        if person_id != previous_person_id and person_id:
            person = Person.objects.select_related("limits_tpl__current_limits").get(
                pk=person_id
            )

            if person.limits_tpl_id:
                account.limits = person.limits_tpl.current_limits
                account.save(update_fields=("limits", "updated"))

        account.computer.materialize_config()
        return account

    @transaction.atomic
    def store_event_packet(
        self,
        packet: ParsedEventPacket,
        byte_size: int,
        remote_ip: str | None,
    ) -> tuple[EventPacket, bool]:
        """Idempotently store one validated packet and all of its events."""
        account = (
            type(self)
            .objects.select_for_update()
            .select_related("computer")
            .get(pk=self.pk)
        )
        computer = account.computer
        computer.ensure_synchronization_allowed()

        if not account.collect:
            raise ClientAccessError("Event collection is disabled for this account")

        packet_manager = EventPacket.objects
        existing_packet = packet_manager.filter(
            account=account,
            sha256=packet.sha256,
        ).first()

        if existing_packet is not None:
            computer.record_contact(remote_ip)
            return existing_packet, False

        events = packet.events
        sequences = {event.seq for event in events}
        stored_sequences = set(
            ActivityEvent.objects.filter(
                account=account,
                seq__gte=packet.first_seq,
                seq__lte=packet.last_seq,
            ).values_list("seq", flat=True)
        )
        conflicts = sequences & stored_sequences

        if conflicts:
            conflict = min(conflicts)
            raise EventSequenceConflictError(
                f"Event sequence {conflict} is already stored for UID {account.uid}"
            )

        packet_record = packet_manager.create(
            account=account,
            sha256=packet.sha256,
            first_seq=packet.first_seq,
            last_seq=packet.last_seq,
            event_count=len(events),
            byte_size=byte_size,
        )
        ActivityEvent.objects.bulk_create(
            ActivityEvent.build_from_client_event(account, packet_record, event)
            for event in events
        )
        computer.record_contact(remote_ip)
        return packet_record, True

    def build_client_config(self) -> ClientAccount:
        """Build this account in the shared sanex configuration format."""
        limits = self.limits.build_client_config() if self.limits_id else None
        return ClientAccount(
            uid=self.uid,
            collect=self.collect,
            apply=self.apply,
            limits=limits,
        )

    def clean(self) -> None:
        """Validate observation flags and limits assignment."""
        super().clean()
        errors = {}
        apply_limits = self.apply

        if apply_limits and not self.collect:
            errors["apply"] = _("Applying limits requires event collection.")

        if apply_limits and not self.limits_id:
            errors["limits"] = _("Applying limits requires a limits set.")

        if errors:
            raise ValidationError(errors)
