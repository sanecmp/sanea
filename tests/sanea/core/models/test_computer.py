"""Tests for registered computers."""

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from django.core.exceptions import ValidationError

from sanea.core.models.computer import Computer


def test_uses_familiar_name_with_hostname_fallback(
    domain_payload: dict[str, Any],
) -> None:
    computer = Computer(**domain_payload["computer"])

    assert computer.get_display_name() == computer.hostname

    computer.name = "Bedroom computer"

    assert computer.get_display_name() == "Bedroom computer"
    assert f"{computer}" == "Bedroom computer"


def test_validates_intervals_and_timezone(domain_payload: dict[str, Any]) -> None:
    computer = Computer(**domain_payload["computer"])
    computer.discovery_interval = computer.sync_interval + 1
    computer.walk_interval = computer.save_interval + 1
    computer.timezone = "Not/A-Timezone"

    with pytest.raises(ValidationError) as error:
        computer.full_clean()

    assert set(error.value.message_dict) == {
        "discovery_interval",
        "timezone",
        "walk_interval",
    }


@pytest.mark.parametrize(
    ("elapsed", "expected"),
    [
        (0, "online"),
        (600, "online"),
        (601, "overdue"),
        (1_500, "overdue"),
        (1_501, "offline"),
    ],
)
def test_classifies_connection_by_synchronization_intervals(
    domain_payload: dict[str, Any],
    elapsed: int,
    expected: str,
) -> None:
    computer = Computer(**domain_payload["computer"])
    computer.sync_interval = 300
    now = datetime(2026, 10, 3, 12, tzinfo=UTC)
    computer.last_seen = now - timedelta(seconds=elapsed)

    assert computer.get_connection_status(now) == expected


def test_classifies_never_seen_computer_as_offline(
    domain_payload: dict[str, Any],
) -> None:
    computer = Computer(**domain_payload["computer"])
    computer.last_seen = None

    assert computer.get_connection_status() == "offline"
