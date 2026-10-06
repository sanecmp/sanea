"""Reusable validators for sanea domain models."""

from django.core.validators import MinValueValidator, RegexValidator
from django.utils.translation import gettext_lazy as _


NON_NEGATIVE = MinValueValidator(0)
FINGERPRINT = RegexValidator(
    regex=r"^[0-9a-f]{64}$",
    message=_("Fingerprint must contain 64 lowercase hexadecimal characters."),
)
