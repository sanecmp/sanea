"""Weekly schedule presentation and parsing helpers."""

import re

from django.utils.translation import gettext_lazy as _


WEEKDAY_CHOICES = (
    (0, _("Monday")),
    (1, _("Tuesday")),
    (2, _("Wednesday")),
    (3, _("Thursday")),
    (4, _("Friday")),
    (5, _("Saturday")),
    (6, _("Sunday")),
)
_CLOCK_PATTERN = re.compile(r"^(?P<hour>\d{2}):(?P<minute>\d{2})$")


def parse_clock(value: str, *, allow_24: bool = False) -> int:
    """Convert an HH:MM clock value to minutes since midnight."""
    match = _CLOCK_PATTERN.fullmatch(value)

    if not match:
        raise ValueError

    hour = int(match.group("hour"))
    minute = int(match.group("minute"))

    if hour == 24 and minute == 0 and allow_24:
        return 1_440

    if hour > 23 or minute > 59:
        raise ValueError

    return hour * 60 + minute


def format_clock(value: int) -> str:
    """Convert minutes since midnight to HH:MM, preserving 24:00."""
    hour, minute = divmod(value, 60)
    return f"{hour:02d}:{minute:02d}"
