"""Tests for activity presentation filters."""

from datetime import UTC, datetime

import pytest
from django.utils import timezone

from sanea.core.templatetags.activity import activity_datetime, activity_duration


@pytest.mark.parametrize(
    ("seconds", "expected"),
    [(None, "—"), (0, "0:00"), (-1, "0:00"), (61, "1:01"), (3661, "1:01:01")],
)
def test_duration_distinguishes_unknown_from_recorded_zero(seconds: int | None, expected: str) -> None:
    assert activity_duration(seconds) == expected


def test_datetime_uses_the_current_sanea_timezone() -> None:
    timestamp = int(datetime(2026, 10, 2, 2, tzinfo=UTC).timestamp())

    with timezone.override("America/New_York"):
        result = activity_datetime(timestamp)

    assert result.isoformat() == "2026-10-01T22:00:00-04:00"
    assert activity_datetime(None) is None
