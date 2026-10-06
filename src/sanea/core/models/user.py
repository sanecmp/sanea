"""Browser user model."""

from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils.translation import gettext_lazy as _

from .person import Person


class User(AbstractUser):
    """Browser user optionally associated with a represented person."""

    person = models.ForeignKey(
        Person,
        verbose_name=_("Person"),
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="users",
        help_text=_("Optional person represented by this browser user."),
    )
