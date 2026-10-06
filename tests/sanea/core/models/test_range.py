"""Tests for weekly schedule ranges."""

from typing import Any

import pytest
from django.core.exceptions import ValidationError

from sanea.core.models.limits import Limits
from sanea.core.models.range import Range
from sanea.core.models.session_rule import SessionRule


def test_must_not_cross_or_overlap(domain_graph: dict[str, Any]) -> None:
    range_ = domain_graph["range"]
    overlapping = Range(
        limits=range_.limits,
        ident=502,
        weekday=range_.weekday,
        since=range_.till - 1,
        till=range_.till + 60,
        session_rule=range_.session_rule,
    )

    with pytest.raises(ValidationError, match="overlap"):
        overlapping.full_clean()

    range_.since = range_.till

    with pytest.raises(ValidationError):
        range_.full_clean()


def test_rule_must_belong_to_same_limits(domain_graph: dict[str, Any]) -> None:
    range_ = domain_graph["range"]
    other_limits = Limits.objects.create(name="Other")
    other_rule = SessionRule.objects.create(limits=other_limits, ident=602, name="Other")
    range_.session_rule = other_rule

    with pytest.raises(ValidationError, match="same limits"):
        range_.full_clean()
