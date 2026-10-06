"""Tests spanning the complete sanea domain graph."""

from typing import Any

from pytest_djangoapp.fixtures.db import Queries

from sanea.core.models.account import Account


def test_complete_domain_graph(domain_graph: dict[str, Any], db_queries: Queries) -> None:
    account = domain_graph["account"]

    with db_queries.scope(expect=1):
        loaded = Account.objects.select_related("computer", "person", "limits").get(pk=account.pk)

    assert loaded.computer.hostname == "child-laptop"
    assert loaded.person.name == "Иван"
    assert loaded.limits.ranges.get().session_rule.app_rules.get().name == "Browser"
    assert loaded.person.limits_tpl.current_limits != loaded.limits
