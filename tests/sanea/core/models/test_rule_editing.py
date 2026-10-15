"""All limits rule forms preserve assigned snapshots and roll back together."""

from typing import Any
from unittest.mock import Mock

import pytest

from sanea.core.forms import AppRuleForm, RangeForm, SessionRuleForm
from sanea.core.models import IdentifierSequence, Limits, SessionRule
from sanea.core.models.base import TimestampedModel


@pytest.mark.parametrize("new_rule", [False, True], ids=["edit", "create"])
def test_rule_forms_fork_assigned_limits_and_preserve_the_source(
    limits_rule_form: tuple[SessionRuleForm | RangeForm | AppRuleForm, Limits | SessionRule, TimestampedModel],
    limits_snapshot_graph: dict[str, Any], new_rule: bool,
) -> None:
    form, parent, source = limits_rule_form
    original_values = source.get_editable_values()
    model = type(source)
    graph = limits_snapshot_graph
    source_limits = graph["limits"]
    template = graph["template"]
    assert form.is_valid(), form.errors

    saved = model.save_form(form, parent)
    template.refresh_from_db()
    source.refresh_from_db()
    graph["account"].refresh_from_db()

    assert template.current_limits_id != source_limits.pk
    assert graph["account"].limits_id == source_limits.pk
    assert source.get_editable_values() == original_values
    assert saved.pk != source.pk
    assert (saved.ident != source.ident) == new_rule
    target = template.current_limits
    target_rule = target.session_rules.get(ident=graph["session_rule"].ident)
    rules = {
        "sessionrule": target.session_rules,
        "range": target.ranges,
        "apprule": target_rule.app_rules,
    }[model._meta.model_name]
    assert rules.get(pk=saved.pk) == saved
    assert rules.count() == 1 + int(new_rule)
    saved.full_clean()


@pytest.mark.parametrize("new_rule", [False, True], ids=["edit", "create"])
def test_rule_forms_roll_back_the_fork_and_identifier_after_publication_failure(
    limits_rule_form: tuple[SessionRuleForm | RangeForm | AppRuleForm, Limits | SessionRule, TimestampedModel],
    limits_snapshot_graph: dict[str, Any], new_rule: bool, monkeypatch: pytest.MonkeyPatch,
) -> None:
    form, parent, source = limits_rule_form
    original_values = source.get_editable_values()
    model = type(source)
    limits_count = Limits.objects.count()
    rule_count = model.objects.count()
    sequences = list(IdentifierSequence.objects.values())
    template = limits_snapshot_graph["template"]
    original_limits_id = template.current_limits_id
    monkeypatch.setattr(Limits, "materialize_computer_configs", Mock(side_effect=RuntimeError("publication failed")))
    assert form.is_valid(), form.errors

    with pytest.raises(RuntimeError, match="publication failed"):
        model.save_form(form, parent)

    template.refresh_from_db()
    source.refresh_from_db()
    assert template.current_limits_id == original_limits_id
    assert source.get_editable_values() == original_values
    assert Limits.objects.count() == limits_count
    assert model.objects.count() == rule_count
    assert list(IdentifierSequence.objects.values()) == sequences
