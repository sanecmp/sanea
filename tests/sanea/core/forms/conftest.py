"""Data-backed fixtures for activity filter form tests."""

import json
from pathlib import Path
from typing import Any

import pytest

from sanea.core.models import Account, Computer, Person


@pytest.fixture
def activity_filter_payload(datafix_dir: Path) -> dict[str, Any]:
    """Load representative activity-filter records."""
    return json.loads((datafix_dir / "activity_filters.json").read_text())


@pytest.fixture
def activity_filter_records(
    activity_filter_payload: dict[str, Any],
) -> dict[str, Account | Computer | Person]:
    """Create monitored and unrelated filter choices."""
    payload = activity_filter_payload
    computer = Computer.objects.create(**payload["computer"])
    other_computer = Computer.objects.create(**payload["other_computer"])
    person = Person.objects.create(**payload["person"])
    other_person = Person.objects.create(**payload["other_person"])
    account = Account.objects.create(
        computer=computer,
        person=person,
        **payload["account"],
    )
    other_account = Account.objects.create(
        computer=other_computer,
        person=other_person,
        uid=1002,
        login="maya",
        name="Maya",
        collect=True,
    )
    return {
        "account": account,
        "computer": computer,
        "other_account": other_account,
        "other_computer": other_computer,
        "person": person,
        "other_person": other_person,
    }
