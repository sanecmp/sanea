"""Data-backed fixtures for sanea core model tests."""

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from sanea.core.models import (
    Account,
    ActivityEvent,
    AppRule,
    ClientCommand,
    Computer,
    ComputerConfig,
    EventPacket,
    Limits,
    LimitsTemplate,
    Person,
    Range,
    SessionRule,
)
from sanea.core.models.base import TimestampedModel


@pytest.fixture
def activity_events_content(datafix_dir: Path) -> bytes:
    """Load one representative exact JSONL event packet."""
    return (datafix_dir / "activity_events.jsonl").read_bytes()


@pytest.fixture
def domain_payload(datafix_dir: Path) -> dict[str, Any]:
    """Load one complete representative domain graph."""
    return json.loads((datafix_dir / "domain.json").read_text())


@pytest.fixture
def domain_graph(domain_payload: dict[str, Any]) -> dict[str, Any]:
    """Create and validate one complete account configuration graph."""
    computer = Computer(**domain_payload["computer"])
    computer.full_clean()
    computer.save()

    template_limits = Limits.objects.create(**domain_payload["template"])
    template = LimitsTemplate.objects.create(
        name=template_limits.name,
        current_limits=template_limits,
    )
    person = Person(limits_tpl=template, **domain_payload["person"])
    person.full_clean()
    person.save()

    limits = Limits.objects.create(**domain_payload["limits"])
    account = Account(
        computer=computer,
        person=person,
        limits=limits,
        **domain_payload["account"],
    )
    account.full_clean()
    account.save()

    session_rule = SessionRule(limits=limits, **domain_payload["session_rule"])
    session_rule.full_clean()
    session_rule.save()

    range_ = Range(
        limits=limits,
        session_rule=session_rule,
        **domain_payload["range"],
    )
    range_.full_clean()
    range_.save()

    app_rule = AppRule(session_rule=session_rule, **domain_payload["app_rule"])
    app_rule.full_clean()
    app_rule.save()

    return {
        "computer": computer,
        "template": template,
        "template_limits": template_limits,
        "person": person,
        "limits": limits,
        "account": account,
        "session_rule": session_rule,
        "range": range_,
        "app_rule": app_rule,
    }


@pytest.fixture
def representation_record(
    domain_graph: dict[str, Any],
) -> Callable[[str], tuple[TimestampedModel | ComputerConfig, str]]:
    """Create only the records needed by one string-representation scenario."""
    account = domain_graph["account"]
    computer = domain_graph["computer"]

    def create(kind: str) -> tuple[TimestampedModel | ComputerConfig, str]:

        if kind == "account":
            return account, f"{account.login} ({account.uid}@{account.computer_id})"

        if kind == "command":
            command = ClientCommand.objects.create(computer=computer, type="refresh")
            return command, f"{computer.pk} #{command.pk}: refresh"

        if kind == "config":
            config = computer.materialize_config()
            return config, f"{computer.pk} #{config.ident}"

        packet = EventPacket.objects.create(
            account=account,
            sha256="a" * 64,
            first_seq=17,
            last_seq=17,
            event_count=1,
            byte_size=64,
        )

        if kind == "packet":
            return packet, f"{account.pk} 17-17"

        event = ActivityEvent.objects.create(
            account=account,
            packet=packet,
            seq=17,
            type="session_start",
            timestamp=1_700_000_000,
        )
        return event, f"session_start #17 ({account.pk})"

    return create


@pytest.fixture
def limits_snapshot_payload(datafix_dir: Path) -> dict[str, Any]:
    """Load one representative shared snapshot graph."""
    return json.loads((datafix_dir / "limits_snapshots.json").read_text())


@pytest.fixture
def limits_snapshot_graph(
    limits_snapshot_payload: dict[str, Any],
) -> dict[str, Any]:
    """Create a template snapshot assigned to one person's account."""
    payload = limits_snapshot_payload
    computer = Computer.objects.create(**payload["computer"])
    limits = Limits.objects.create(**payload["limits"])
    limits_template = LimitsTemplate.objects.create(
        name=limits.name,
        current_limits=limits,
    )
    person = Person.objects.create(
        limits_tpl=limits_template,
        **payload["person"],
    )
    account = Account.objects.create(
        computer=computer,
        person=person,
        limits=limits,
        **payload["account"],
    )
    session_rule = SessionRule.objects.create(
        limits=limits,
        **payload["session_rule"],
    )
    app_rule = AppRule.objects.create(
        session_rule=session_rule,
        **payload["app_rule"],
    )
    range_ = Range.objects.create(
        limits=limits,
        session_rule=session_rule,
        **payload["range"],
    )
    return {
        "account": account,
        "computer": computer,
        "app_rule": app_rule,
        "limits": limits,
        "person": person,
        "range": range_,
        "session_rule": session_rule,
        "template": limits_template,
    }
