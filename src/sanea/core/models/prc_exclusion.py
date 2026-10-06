"""Globally ignored process names sent to every sanex computer."""

from django.apps import apps
from django.core.validators import MaxLengthValidator
from django.db import models, transaction
from django.utils.translation import gettext_lazy as _

from .base import TimestampedModel


DEFAULT_IGNORED_PRCS = (
    "gnome-control-c",
    "gnome-software",
    "gnome-system-mo",
    "gnome-tweaks",
    "nautilus",
)


class PrcExclusion(TimestampedModel):
    """One exact Linux process name excluded from activity accounting."""

    prc_name = models.CharField(
        verbose_name=_("Process name"),
        max_length=15,
        unique=True,
        validators=[MaxLengthValidator(15)],
        help_text=_(
            "Exact case-sensitive name from /proc/PID/comm, up to 15 characters."
        ),
    )
    apply = models.BooleanField(
        verbose_name=_("Ignore process"),
        default=True,
        editable=False,
        help_text=_("Include this exact name in configurations sent to sanex."),
    )

    class Meta:
        verbose_name = _("Ignored process")
        verbose_name_plural = _("Ignored processes")
        ordering = ("prc_name", "pk")

    def __str__(self) -> str:
        return self.prc_name

    @classmethod
    def get_names(cls) -> tuple[str, ...]:
        """Return all ignored names in deterministic configuration order."""
        return tuple(
            cls.objects.filter(apply=True)
            .order_by("prc_name", "pk")
            .values_list("prc_name", flat=True)
        )

    @classmethod
    def install_defaults(cls) -> None:
        """Create packaged defaults without re-enabling user-disabled rows."""

        for prc_name in DEFAULT_IGNORED_PRCS:
            cls.objects.get_or_create(prc_name=prc_name)

    @classmethod
    @transaction.atomic
    def create_and_materialize(cls, prc_name: str) -> "PrcExclusion":
        """Create a validated exclusion and refresh every computer config."""
        exclusion = cls(prc_name=prc_name)
        exclusion.full_clean()
        exclusion.save()
        cls._materialize_configs()
        return exclusion

    @transaction.atomic
    def delete_and_materialize(self) -> None:
        """Disable this exclusion and refresh every computer config."""
        self._set_application_and_materialize(False)

    @transaction.atomic
    def restore_and_materialize(self) -> None:
        """Restore this exclusion and refresh every computer config."""
        self._set_application_and_materialize(True)

    def _set_application_and_materialize(self, apply: bool) -> None:

        if self.apply == apply:
            return

        self.apply = apply
        self.save(update_fields=("apply", "updated"))
        type(self)._materialize_configs()

    @classmethod
    def _materialize_configs(cls) -> None:
        computer_model = apps.get_model("core", "Computer")
        computer_ids = computer_model.objects.values_list("pk", flat=True)
        computer_model.materialize_configs(computer_ids)
