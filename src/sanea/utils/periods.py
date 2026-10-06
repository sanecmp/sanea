"""Shared reporting-period definitions."""

from django.db.models import TextChoices
from django.utils.translation import gettext_lazy as _


class ReportingPeriod(TextChoices):
    """Date ranges supported by browser reports."""

    TODAY = "today", _("Today")
    DAYS_7 = "7-days", _("Last 7 days")
    DAYS_30 = "30-days", _("Last 30 days")
    ALL = "all", _("All time")

    def get_day_count(self) -> int | None:
        """Return the inclusive day count or no bound for all time."""
        return {
            self.TODAY: 1,
            self.DAYS_7: 7,
            self.DAYS_30: 30,
            self.ALL: None,
        }[self]
