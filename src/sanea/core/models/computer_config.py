"""Materialized sanex configuration model."""

from sanelib.exceptions import ProtocolError
from sanelib.protocol import Config as ClientConfig, parse_config
from django.db import models
from django.utils.translation import gettext_lazy as _

from ...exceptions import ComputerConfigError


class ComputerConfig(models.Model):
    """An immutable ready-to-send configuration for one computer."""

    ident = models.BigAutoField(
        primary_key=True,
        verbose_name=_("Identifier"),
    )
    computer = models.ForeignKey(
        "Computer",
        verbose_name=_("Computer"),
        on_delete=models.CASCADE,
        related_name="configs",
    )
    created = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_("Created"),
    )
    payload = models.BinaryField(
        verbose_name=_("JSON payload"),
        help_text=_("Complete ready-to-send sanex configuration."),
    )

    class Meta:
        verbose_name = _("Computer configuration")
        verbose_name_plural = _("Computer configurations")
        ordering = ("-ident",)

    def __str__(self) -> str:
        return f"{self.computer_id} #{self.ident}"

    def decode(self) -> ClientConfig:
        """Decode and validate the stored shared configuration."""
        ident = self.ident
        try:
            config = parse_config(bytes(self.payload))

        except ProtocolError as error:
            raise ComputerConfigError(
                f"Computer configuration {ident} is invalid: {error}"
            ) from error

        if config.ident != ident:
            raise ComputerConfigError(
                f"Computer configuration {ident} has an invalid identifier"
            )

        return config

    def extract_body_without_ident(self) -> dict[str, object]:
        """Return a validated JSON-compatible body for content comparison."""
        return self.decode().model_dump(mode="json", exclude={"ident"})
