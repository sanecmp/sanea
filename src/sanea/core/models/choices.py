"""Choice enums shared by sanea domain models."""

from django.db import models
from django.utils.translation import gettext_lazy as _, pgettext_lazy
from sanelib.protocol import CommandStatus as ClientCommandStatus, MatchType as ClientMatchType


class ComputerStatus(models.TextChoices):
    """Registration and access state of a sanex computer."""

    PENDING = "pending", _("Pending")
    ALLOWED = "allowed", _("Allowed")
    BLOCKED = "blocked", _("Blocked")


class ConnectionStatus(models.TextChoices):
    """Freshness of the latest authenticated contact from sanex."""

    ONLINE = "online", _("Online")
    OVERDUE = "overdue", _("Overdue")
    OFFLINE = "offline", _("Offline")


class ConfigDeliveryStatus(models.TextChoices):
    """Whether sanex has confirmed the latest materialized configuration."""

    WAITING = "waiting", _("Waiting for sync")
    APPLIED = "applied", pgettext_lazy("configuration delivery status", "Applied")


class MatchType(models.TextChoices):
    """Supported application recognition methods."""

    EXACT = ClientMatchType.EXACT.value, _("Exact")
    CONTAINS = ClientMatchType.CONTAINS.value, _("Contains")
    REGEX = ClientMatchType.REGEX.value, _("Regular expression")


class CommandStatus(models.TextChoices):
    """Terminal states reported after a client command."""

    DONE = ClientCommandStatus.DONE.value, _("Done")
    FAILED = ClientCommandStatus.FAILED.value, _("Failed")
