"""Registered sanex computer model."""

import ipaddress
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Self
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from collections.abc import Iterable

from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models, transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from pydantic import ValidationError as PydanticValidationError
from sanelib.protocol import Config as ClientConfig, encode_config
from django.db.models import QuerySet

from ...exceptions import ClientAccessError, ClientRequestError, ComputerConfigError
from .account import Account
from .base import TimestampedModel
from .choices import CommandStatus, ComputerStatus, ConfigDeliveryStatus, ConnectionStatus
from .client_command import ClientCommand
from .computer_config import ComputerConfig
from .limits import Limits
from .prc_exclusion import PrcExclusion
from .validation import FINGERPRINT

if TYPE_CHECKING:
    from ..forms import ComputerForm
    from sanelib.protocol import CommandResult, DiscoveredAccount

@dataclass(frozen=True, slots=True)
class ConnectionCounts:
    """Computer totals grouped by connection freshness."""

    online: int
    overdue: int
    offline: int


class Computer(TimestampedModel):
    """One registered computer running sanex."""

    name = models.CharField(
        verbose_name=_("Name"),
        max_length=160,
        blank=True,
        help_text=_("A familiar name shown in the web interface."),
    )
    hostname = models.CharField(
        verbose_name=_("Hostname"),
        max_length=253,
        help_text=_("Hostname most recently reported by sanex."),
    )
    version = models.CharField(
        verbose_name=_("Version"),
        max_length=64,
        blank=True,
        help_text=_("Installed sanex package version."),
    )
    status = models.CharField(
        verbose_name=_("Status"),
        max_length=16,
        choices=ComputerStatus,
        default=ComputerStatus.PENDING,
        help_text=_("Registration and client-access state."),
    )
    certificate_fingerprint = models.CharField(
        verbose_name=_("Client certificate fingerprint"),
        max_length=64,
        unique=True,
        null=True,
        blank=True,
        validators=[FINGERPRINT],
        help_text=_("SHA-256 fingerprint of the issued client certificate."),
    )
    public_key_fingerprint = models.CharField(
        verbose_name=_("Public key fingerprint"),
        max_length=64,
        unique=True,
        null=True,
        blank=True,
        validators=[FINGERPRINT],
        help_text=_("SHA-256 fingerprint of the registration CSR public key."),
    )
    client_certificate = models.TextField(
        verbose_name=_("Client certificate"),
        blank=True,
        editable=False,
        help_text=_("Issued client certificate retained for registration recovery."),
    )
    last_ip = models.GenericIPAddressField(
        verbose_name=_("Last IP address"),
        null=True,
        blank=True,
        help_text=_("Source address of the latest authenticated request."),
    )
    last_seen = models.DateTimeField(
        verbose_name=_("Last seen"),
        null=True,
        blank=True,
        help_text=_("Time of the latest authenticated request."),
    )
    log_tail = models.TextField(
        verbose_name=_("Technical log"),
        blank=True,
        editable=False,
        help_text=_("Latest diagnostic log received from sanex."),
    )
    log_received = models.DateTimeField(
        verbose_name=_("Technical log received"),
        null=True,
        blank=True,
        editable=False,
        help_text=_("Server time when the latest diagnostic log was received."),
    )
    timezone = models.CharField(
        verbose_name=_("Timezone"),
        max_length=64,
        default="UTC",
        help_text=_("IANA timezone used to evaluate weekly schedules."),
    )
    sync_interval = models.PositiveIntegerField(
        verbose_name=_("Synchronization interval"),
        default=300,
        validators=[MinValueValidator(10), MaxValueValidator(86_400)],
        help_text=_("Seconds between successful complete synchronization cycles."),
    )
    discovery_interval = models.PositiveIntegerField(
        verbose_name=_("Discovery interval"),
        default=30,
        validators=[MinValueValidator(1)],
        help_text=_(
            "Seconds between discovery attempts while synchronization is required."
        ),
    )
    walk_interval = models.PositiveIntegerField(
        verbose_name=_("Walk interval"),
        default=1,
        validators=[MinValueValidator(1)],
        help_text=_("Maximum seconds between session, window and process scans."),
    )
    save_interval = models.PositiveIntegerField(
        verbose_name=_("Save interval"),
        default=5,
        validators=[MinValueValidator(1), MaxValueValidator(300)],
        help_text=_("Maximum seconds between persistent runtime-state saves."),
    )
    min_prc_duration = models.PositiveIntegerField(
        verbose_name=_("Minimum process duration"),
        default=5,
        validators=[MaxValueValidator(60)],
        help_text=_("Minimum process duration in seconds retained in statistics."),
    )
    current_config = models.ForeignKey(
        "ComputerConfig",
        verbose_name=_("Current configuration"),
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        editable=False,
        related_name="current_for_computers",
        help_text=_("Configuration currently offered to this computer."),
    )
    applied_config = models.ForeignKey(
        "ComputerConfig",
        verbose_name=_("Applied configuration"),
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        editable=False,
        related_name="applied_for_computers",
        help_text=_("Configuration most recently confirmed by sanex."),
    )

    class Meta:
        verbose_name = _("Computer")
        verbose_name_plural = _("Computers")
        ordering = ("hostname", "pk")

    def __str__(self) -> str:
        return self.get_display_name()

    def get_display_name(self) -> str:
        """Return the familiar name, falling back to the reported hostname."""
        return self.name or self.hostname

    def get_config_delivery_status(self) -> ConfigDeliveryStatus:
        """Return whether sanex confirmed the latest offered configuration."""
        current_config_id = self.current_config_id

        if current_config_id and self.applied_config_id == current_config_id:
            return ConfigDeliveryStatus.APPLIED

        return ConfigDeliveryStatus.WAITING

    @transaction.atomic
    def acknowledge_config(self, ident: int | None) -> None:
        """Record the applied config and discard superseded immutable data."""
        config = None

        if ident is not None:
            config = self.configs.filter(pk=ident).first()

            if config is None:
                raise ClientRequestError(
                    f"Configuration {ident} does not belong to computer {self.pk}"
                )

        if self.applied_config_id != ident:
            self.applied_config = config
            self.save(update_fields=("applied_config", "updated"))

        self.delete_obsolete_configs()
        Limits.delete_unreferenced()

    def delete_obsolete_configs(self) -> int:
        """Delete configs other than the current and confirmed snapshots."""
        protected = {
            ident
            for ident in (self.current_config_id, self.applied_config_id)
            if ident is not None
        }
        configs = self.configs.exclude(pk__in=protected)
        count = configs.count()
        configs.delete()
        return count

    def get_connection_status(self, now: datetime | None = None) -> ConnectionStatus:
        """Classify contact freshness using the configured synchronization interval."""
        last_seen = self.last_seen

        if last_seen is None:
            return ConnectionStatus.OFFLINE

        current = now or timezone.now()
        elapsed = max((current - last_seen).total_seconds(), 0)
        interval = self.sync_interval

        if elapsed <= interval * 2:
            return ConnectionStatus.ONLINE

        if elapsed <= interval * 5:
            return ConnectionStatus.OVERDUE

        return ConnectionStatus.OFFLINE

    @classmethod
    def filter_for_overview(
        cls,
        *,
        access: str | None = None,
        connection: str | None = None,
        config_delivery: str | None = None,
    ) -> models.QuerySet[Self]:
        """Return computers matching browser-list operational filters."""
        computers = cls.objects.all()

        if access is not None:
            computers = computers.filter(status=access)

        if config_delivery is not None:
            applied = cls.objects.filter(
                current_config__isnull=False,
                current_config_id=models.F("applied_config_id"),
            )

            if config_delivery == ConfigDeliveryStatus.APPLIED:
                computers = computers.filter(pk__in=applied)

            else:
                computers = computers.exclude(pk__in=applied)

        if connection is not None:
            current = timezone.now()
            matching_ids = [
                computer.pk
                for computer in computers.only("last_seen", "sync_interval")
                if computer.get_connection_status(current) == connection
            ]
            computers = computers.filter(pk__in=matching_ids)

        return computers

    @classmethod
    def count_waiting_configs(cls) -> int:
        """Count computers that have not confirmed their latest configuration."""
        total = cls.objects.count()
        applied = cls.objects.filter(
            current_config__isnull=False,
            current_config_id=models.F("applied_config_id"),
        ).count()
        return total - applied

    @classmethod
    def count_connection_statuses(
        cls,
        now: datetime | None = None,
    ) -> ConnectionCounts:
        """Count registered computers by current connection freshness."""
        current = now or timezone.now()
        counts = {status: 0 for status in ConnectionStatus}

        for computer in cls.objects.only("last_seen", "sync_interval"):
            status = computer.get_connection_status(current)
            counts[status] += 1

        return ConnectionCounts(
            online=counts[ConnectionStatus.ONLINE],
            overdue=counts[ConnectionStatus.OVERDUE],
            offline=counts[ConnectionStatus.OFFLINE],
        )

    @classmethod
    def materialize_configs(cls, computer_ids: Iterable[int]) -> tuple["ComputerConfig", ...]:
        """Materialize current configurations for the selected computers."""
        identifiers = set(computer_ids)

        if not identifiers:
            return ()

        return tuple(
            computer.materialize_config()
            for computer in cls.objects.filter(pk__in=identifiers).order_by("pk")
        )

    @classmethod
    @transaction.atomic
    def save_form(cls, form: "ComputerForm") -> Self:
        """Persist settings and immediately materialize their client config."""
        computer = form.save()
        config = computer.materialize_config()
        computer.current_config = config
        return computer

    @classmethod
    def get_diagnostic_logs(cls, computer: Self | None=None, since: int | None = None) -> models.QuerySet[Self]:
        """Return computers with diagnostic logs received in the selected period."""
        computers = cls.objects.exclude(log_tail="").exclude(log_received=None)

        if computer is not None:
            computers = computers.filter(pk=computer.pk)

        if since is not None:
            computers = computers.filter(
                log_received__gte=datetime.fromtimestamp(since, UTC)
            )

        return computers.order_by("-log_received", "hostname", "pk")

    @classmethod
    def has_pending_registration(cls) -> bool:
        """Return whether a client may resume registration confirmation."""
        return cls.objects.filter(status=ComputerStatus.PENDING).exists()

    @classmethod
    def create_pending_registration(
        cls,
        *,
        hostname: str,
        public_key_fingerprint: str,
        certificate_fingerprint: str,
        client_certificate: str,
    ) -> Self:
        """Create a computer awaiting authenticated confirmation."""
        return cls.objects.create(
            hostname=hostname,
            status=ComputerStatus.PENDING,
            public_key_fingerprint=public_key_fingerprint,
            certificate_fingerprint=certificate_fingerprint,
            client_certificate=client_certificate,
        )

    def ensure_registration_confirmation_allowed(self) -> None:
        """Reject confirmation for a blocked or otherwise invalid state."""

        if self.status not in (ComputerStatus.PENDING, ComputerStatus.ALLOWED):
            raise ClientAccessError("Computer is not allowed to complete registration")

    def ensure_synchronization_allowed(self) -> None:
        """Reject synchronization until registration is allowed."""

        if self.status != ComputerStatus.ALLOWED:
            raise ClientAccessError("Computer is not allowed to synchronize")

    def apply_command_results(
        self,
        results: tuple["CommandResult", ...],
    ) -> None:
        """Apply terminal command results belonging to this computer."""

        if not results:
            return

        result_idents = [result.ident for result in results]
        commands = {
            command.pk: command
            for command in ClientCommand.objects.select_for_update().filter(
                computer=self,
                pk__in=result_idents,
            )
        }
        completed = timezone.now()

        for ident, result in zip(result_idents, results, strict=True):
            command = commands.get(ident)

            if command is None:
                raise ClientRequestError(
                    f"Command {ident} does not belong to this computer"
                )

            command.apply_result(
                CommandStatus(result.status.value),
                result.error,
                completed,
            )

    def record_contact(self, remote_ip: str | None) -> None:
        """Record one authenticated request without changing client metadata."""
        self.set_contact(remote_ip)
        self.save(update_fields=("last_ip", "last_seen", "updated"))

    def set_contact(
        self,
        remote_ip: str | None,
        received: datetime | None = None,
    ) -> None:
        """Set in-memory contact fields using one consistent timestamp."""
        self.last_ip = self._normalize_ip(remote_ip)
        self.last_seen = received or timezone.now()

    def update_contact(
        self,
        version: str,
        remote_ip: str | None,
        *,
        hostname: str | None = None,
        status: ComputerStatus | None = None,
    ) -> None:
        """Persist metadata common to authenticated client requests."""
        self.version = version
        self.set_contact(remote_ip)
        changed_fields = ["version", "last_ip", "last_seen"]
        add_changed_field = changed_fields.append

        if hostname is not None:
            self.hostname = hostname
            add_changed_field("hostname")

        if status is not None:
            self.status = status
            add_changed_field("status")

        self.save(update_fields=(*changed_fields, "updated"))

    @transaction.atomic
    def replace_log_tail(self, content: str, remote_ip: str | None) -> None:
        """Atomically replace the latest technical-log snapshot."""
        computer = type(self).objects.select_for_update().get(pk=self.pk)
        computer.ensure_synchronization_allowed()
        received = timezone.now()
        computer.log_tail = content
        computer.log_received = received
        computer.set_contact(remote_ip, received)
        computer.save(
            update_fields=(
                "log_tail",
                "log_received",
                "last_ip",
                "last_seen",
                "updated",
            )
        )

    def apply_account_snapshot(
        self,
        reported_accounts: tuple["DiscoveredAccount", ...],
    ) -> None:
        """Apply a complete account snapshot while preserving local settings."""

        account_manager = Account.objects
        existing = {
            account.uid: account
            for account in account_manager.select_for_update().filter(computer=self)
        }
        reported_uids = set()

        for reported in reported_accounts:
            uid = reported.uid
            login = reported.login
            name = reported.name
            reported_uids.add(uid)
            account = existing.get(uid)

            if account is None:
                account_manager.create(
                    computer=self,
                    uid=uid,
                    login=login,
                    name=name,
                )
                continue

            account.update_report(login, name)

        account_manager.filter(computer=self).exclude(uid__in=reported_uids).update(
            present=False,
            updated=timezone.now(),
        )

    @staticmethod
    def _normalize_ip(value: str | None) -> str | None:

        if not value:
            return None

        try:
            return f"{ipaddress.ip_address(value)}"

        except ValueError:
            return None

    def build_client_config(self, ident: int) -> ClientConfig:
        """Build the complete shared sanex configuration for this computer."""
        accounts = sorted(self.accounts.all(), key=lambda item: (item.uid, item.pk))
        return ClientConfig(
            ident=ident,
            timezone=self.timezone,
            sync_interval=self.sync_interval,
            discovery_interval=self.discovery_interval,
            walk_interval=self.walk_interval,
            save_interval=self.save_interval,
            min_prc_duration=self.min_prc_duration,
            ignored_prcs=PrcExclusion.get_names(),
            accounts=tuple(account.build_client_config() for account in accounts),
        )

    @transaction.atomic
    def materialize_config(self) -> ComputerConfig:
        """Return the current ready payload, creating it when content changed."""

        computer = (
            type(self)
            .objects.select_for_update()
            .select_related("current_config")
            .prefetch_related(
                "accounts__limits__ranges__session_rule",
                "accounts__limits__session_rules__app_rules",
            )
            .get(pk=self.pk)
        )
        try:
            candidate = computer.build_client_config(ident=0)

        except PydanticValidationError as error:
            raise ComputerConfigError(
                "Unable to build a valid sanex configuration"
            ) from error

        candidate_body = candidate.model_dump(mode="json", exclude={"ident"})
        current = computer.current_config

        if current and current.computer_id != computer.pk:
            raise ComputerConfigError(
                f"Computer configuration {current.ident} belongs to another computer"
            )

        if current and current.extract_body_without_ident() == candidate_body:
            return current

        config = ComputerConfig.objects.create(computer=computer, payload=b"")
        candidate = candidate.model_copy(update={"ident": config.ident})
        config.payload = encode_config(candidate)
        config.save(update_fields=("payload",))
        setattr(computer, "current_config", config)
        computer.save(update_fields=("current_config", "updated"))
        return config

    def clean(self) -> None:
        """Validate relationships between synchronization intervals."""
        super().clean()
        errors = {}
        try:
            ZoneInfo(self.timezone)

        except (ValueError, ZoneInfoNotFoundError):
            errors["timezone"] = _("Must be an available IANA timezone name.")

        if self.discovery_interval > self.sync_interval:
            errors["discovery_interval"] = _("Must not exceed sync_interval.")

        if self.walk_interval > self.save_interval:
            errors["walk_interval"] = _("Must not exceed save_interval.")

        pk = self.pk
        config_fields = (
            ("current_config", self.current_config_id),
            ("applied_config", self.applied_config_id),
        )

        for field_name, config_id in config_fields:

            if config_id and pk and getattr(self, field_name).computer_id != pk:
                errors[field_name] = _(
                    "The configuration must belong to this computer."
                )

        if errors:
            raise ValidationError(errors)
