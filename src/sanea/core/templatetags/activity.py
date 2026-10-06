"""Activity report presentation filters."""

from datetime import datetime

from django import template
from django.utils import timezone


register = template.Library()


@register.filter
def activity_duration(value: int | None) -> str:
    """Format seconds as a compact clock-style duration."""
    seconds_total = max(value or 0, 0)
    hours, remainder = divmod(seconds_total, 3_600)
    minutes, seconds = divmod(remainder, 60)

    if hours:
        return f"{hours}:{minutes:02d}:{seconds:02d}"

    return f"{minutes}:{seconds:02d}"


@register.filter
def activity_datetime(value: int | None) -> datetime | None:
    """Convert a Unix timestamp to the current sanea timezone."""

    if value is None:
        return None

    return timezone.datetime.fromtimestamp(value, timezone.get_current_timezone())
