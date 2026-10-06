"""Tests for shared domain-model behavior."""

from collections.abc import Callable
from datetime import timedelta
from typing import Any

import pytest
from time_machine import TimeMachineFixture
from django.utils.functional import Promise
from django.utils.translation import override
from pytest_djangoapp.fixtures.db import Queries

from sanea.core.models import Account, AppRule, Computer, ComputerConfig, Limits, Person, Range, SessionRule
from sanea.core.models.base import TimestampedModel


@pytest.mark.parametrize("kind", ["account", "event", "command", "config", "packet"])
def test_model_representation_does_not_load_relations(
    kind: str,
    representation_record: Callable[[str], tuple[TimestampedModel | ComputerConfig, str]],
    db_queries: Queries,
) -> None:
    record, expected = representation_record(kind)
    loaded = type(record).objects.get(pk=record.pk)

    with db_queries.scope(expect=0):
        assert f"{loaded}" == expected


def test_domain_models_share_automatic_timestamps(
    domain_graph: dict[str, Any],
    time_machine: TimeMachineFixture,
) -> None:
    timestamped_models = (Account, AppRule, Computer, Limits, Person, Range, SessionRule)

    assert all(issubclass(model, TimestampedModel) for model in timestamped_models)
    assert all(domain_graph[key].created for key in domain_graph)
    assert all(domain_graph[key].updated for key in domain_graph)

    account = domain_graph["account"]
    previous_updated = account.updated
    time_machine.move_to(previous_updated, tick=False)
    time_machine.shift(timedelta(seconds=1))
    account.name = "Updated account name"
    account.save()

    assert account.updated == previous_updated + timedelta(seconds=1)


def test_domain_model_names_are_lazy_english_messages() -> None:
    timestamped_models = (Account, AppRule, Computer, Limits, Person, Range, SessionRule)

    for model in timestamped_models:
        assert isinstance(model._meta.verbose_name, Promise)
        assert isinstance(model._meta.verbose_name_plural, Promise)
        assert all(
            isinstance(field.verbose_name, Promise)
            for field in model._meta.fields
            if not field.primary_key
        )

    with override("en"):
        label = Computer._meta.get_field("sync_interval").verbose_name
        assert f"{label}" == "Synchronization interval"
