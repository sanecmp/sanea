"""Tests for application rules."""

from typing import Any

import pytest
from django.core.exceptions import ValidationError

from sanea.core.models.app_rule import AppRule
from sanea.core.models.choices import MatchType
from sanea.core.models.session_rule import SessionRule


def test_requires_limit_and_recognition_condition(domain_graph: dict[str, Any]) -> None:
    rule = domain_graph["app_rule"]
    rule.max_launches = None
    rule.max_time = None
    rule.prc_name = None
    rule.prc_name_match = None

    with pytest.raises(ValidationError) as error:
        rule.full_clean()

    assert set(error.value.message_dict) == {"__all__"}


def test_validates_condition_pair_and_regex(domain_graph: dict[str, Any]) -> None:
    rule = domain_graph["app_rule"]
    rule.prc_name = "["
    rule.prc_name_match = MatchType.REGEX

    with pytest.raises(ValidationError, match="regular expression"):
        rule.full_clean()

    rule.prc_name = None

    with pytest.raises(ValidationError, match="requires its condition"):
        rule.full_clean()


def test_ident_is_unique_within_limits(domain_graph: dict[str, Any]) -> None:
    rule = domain_graph["app_rule"]
    other_session_rule = SessionRule.objects.create(
        limits=rule.session_rule.limits,
        ident=602,
        name="Other",
    )
    duplicate = AppRule(
        session_rule=other_session_rule,
        ident=rule.ident,
        name="Duplicate",
        max_time=1,
        exe="/bin/example",
        exe_match=MatchType.EXACT,
    )

    with pytest.raises(ValidationError, match="unique"):
        duplicate.full_clean()
