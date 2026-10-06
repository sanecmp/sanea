"""Data-backed fixtures for browser view tests."""

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest
from time_machine import TimeMachineFixture

from sanea.core.models import Account, AppRule, Computer, Limits, LimitsTemplate, Person, PrcExclusion, Range, SessionRule


@pytest.fixture(autouse=True)
def calendar_time(time_machine: TimeMachineFixture) -> TimeMachineFixture:
    """Keep reporting periods, contact statuses and command timestamps deterministic."""
    time_machine.move_to("2026-10-06T12:00:00+00:00", tick=False)
    return time_machine


@pytest.fixture
def people_payload(datafix_dir: Path) -> dict[str, Any]:
    """Load representative people form data."""
    return json.loads((datafix_dir / "people.json").read_text())


@pytest.fixture
def ignored_processes_payload(datafix_dir: Path) -> dict[str, Any]:
    """Load representative ignored process names."""
    return json.loads((datafix_dir / "ignored_processes.json").read_text())


@pytest.fixture
def ignored_process_record(
    ignored_processes_payload: dict[str, Any],
) -> PrcExclusion:
    """Create one process exclusion shown by browser views."""
    return PrcExclusion.objects.create(**ignored_processes_payload["existing"])


@pytest.fixture
def person_record(people_payload: dict[str, Any]) -> Person:
    """Create one person shown by browser views."""
    return Person.objects.create(**people_payload["existing"])


@pytest.fixture
def computer_payload(datafix_dir: Path) -> dict[str, Any]:
    """Load a registered computer with one local account."""
    return json.loads((datafix_dir / "computers.json").read_text())


@pytest.fixture
def computer_record(computer_payload: dict[str, Any]) -> Computer:
    """Create a computer and its reported local account."""
    computer_data = dict(computer_payload["computer"])
    computer_data["last_seen"] = datetime.fromisoformat(computer_data["last_seen"])
    computer = Computer.objects.create(**computer_data)
    Account.objects.create(computer=computer, **computer_payload["account"])
    return computer


@pytest.fixture
def limits_payload(datafix_dir: Path) -> dict[str, Any]:
    """Load representative limits editor data."""
    return json.loads((datafix_dir / "limits.json").read_text())


@pytest.fixture
def limits_record(limits_payload: dict[str, Any]) -> Limits:
    """Create one reusable limits template."""
    return Limits.objects.create(**limits_payload["existing"])


@pytest.fixture
def limits_template_record(limits_record: Limits) -> LimitsTemplate:
    """Create one named template pointing to the reusable snapshot."""
    return LimitsTemplate.objects.create(
        name=limits_record.name,
        current_limits=limits_record,
    )


@pytest.fixture
def session_rules_payload(datafix_dir: Path) -> dict[str, Any]:
    """Load representative session rule editor data."""
    return json.loads((datafix_dir / "session_rules.json").read_text())


@pytest.fixture
def session_rule_record(
    limits_record: Limits,
    session_rules_payload: dict[str, Any],
) -> SessionRule:
    """Create one session rule within the representative template."""
    return SessionRule.objects.create(
        limits=limits_record,
        **session_rules_payload["existing"],
    )


@pytest.fixture
def app_rules_payload(datafix_dir: Path) -> dict[str, Any]:
    """Load representative application rule editor data."""
    return json.loads((datafix_dir / "app_rules.json").read_text())


@pytest.fixture
def app_rule_record(
    session_rule_record: SessionRule,
    app_rules_payload: dict[str, Any],
) -> AppRule:
    """Create one application rule within the representative session rule."""
    return AppRule.objects.create(
        session_rule=session_rule_record,
        **app_rules_payload["existing"],
    )


@pytest.fixture
def ranges_payload(datafix_dir: Path) -> dict[str, Any]:
    """Load representative weekly range editor data."""
    return json.loads((datafix_dir / "ranges.json").read_text())


@pytest.fixture
def range_record(
    limits_record: Limits,
    session_rule_record: SessionRule,
    ranges_payload: dict[str, Any],
) -> Range:
    """Create one weekly range within the representative limits set."""
    return Range.objects.create(
        limits=limits_record,
        session_rule=session_rule_record,
        **ranges_payload["existing"],
    )


@pytest.fixture
def client_events_content(datafix_dir: Path) -> bytes:
    """Load one representative exact JSONL event packet."""
    return (datafix_dir / "client_events.jsonl").read_bytes()


@pytest.fixture
def client_registration_payload(datafix_dir: Path) -> dict[str, Any]:
    """Load representative sanex registration metadata."""
    return json.loads((datafix_dir / "client_registration.json").read_text())


@pytest.fixture
def client_registration_confirm_payload(datafix_dir: Path) -> dict[str, Any]:
    """Load representative authenticated registration data."""
    return json.loads((datafix_dir / "client_registration_confirm.json").read_text())


@pytest.fixture
def client_sync_payload(datafix_dir: Path) -> dict[str, Any]:
    """Load one representative sanex synchronization request."""
    return json.loads((datafix_dir / "client_sync.json").read_text())


@pytest.fixture
def updates_payload(datafix_dir: Path) -> dict[str, Any]:
    """Load valid and invalid global sanex update form values."""
    return json.loads((datafix_dir / "updates.json").read_text())
