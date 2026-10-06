"""Tests for immutable limits snapshot operations."""

from typing import Any

from sanea.core.models import Limits


def test_clone_preserves_graph_and_stable_identifiers(
    limits_snapshot_graph: dict[str, Any],
) -> None:
    source = limits_snapshot_graph["limits"]

    target = source.clone("Independent")
    target_rule = target.session_rules.get()

    assert target.pk != source.pk
    assert target.name == "Independent"
    assert target_rule.ident == limits_snapshot_graph["session_rule"].ident
    assert target_rule.app_rules.get().ident == limits_snapshot_graph["app_rule"].ident
    assert target.ranges.get().session_rule == target_rule
    assert target.ranges.get().ident == limits_snapshot_graph["range"].ident


def test_edit_checkout_advances_template_but_keeps_account_snapshot(
    limits_snapshot_graph: dict[str, Any],
) -> None:
    source = limits_snapshot_graph["limits"]
    account = limits_snapshot_graph["account"]
    limits_template = limits_snapshot_graph["template"]

    target = source.checkout_for_edit()
    account.refresh_from_db()
    limits_template.refresh_from_db()

    assert target.pk != source.pk
    assert limits_template.current_limits == target
    assert account.limits == source
    assert target.session_rules.get().ident == source.session_rules.get().ident


def test_account_customization_forks_only_selected_account(
    limits_snapshot_graph: dict[str, Any],
) -> None:
    source = limits_snapshot_graph["limits"]
    account = limits_snapshot_graph["account"]
    limits_template = limits_snapshot_graph["template"]

    target = account.customize_limits()
    account.refresh_from_db()
    limits_template.refresh_from_db()

    assert target.pk != source.pk
    assert account.limits == target
    assert limits_template.current_limits == source
    assert target.session_rules.get().ident == source.session_rules.get().ident


def test_explicit_propagation_repoints_account_and_preserves_flags(
    limits_snapshot_graph: dict[str, Any],
) -> None:
    account = limits_snapshot_graph["account"]
    person = limits_snapshot_graph["person"]
    current = limits_snapshot_graph["template"].current_limits
    account.customize_limits()

    count = person.propagate_template([account])
    account.refresh_from_db()

    assert count == 1
    assert account.limits == current
    assert account.collect is True
    assert account.apply is False


def test_config_acknowledgement_deletes_unreferenced_limits_snapshots(
    limits_snapshot_graph: dict[str, Any],
) -> None:
    source = limits_snapshot_graph["limits"]
    account = limits_snapshot_graph["account"]
    person = limits_snapshot_graph["person"]
    computer = limits_snapshot_graph["computer"]
    target = source.checkout_for_edit()
    person.propagate_template([account])
    computer.refresh_from_db()

    assert Limits.objects.filter(pk=source.pk).exists()
    computer.acknowledge_config(computer.current_config_id)

    assert not Limits.objects.filter(pk=source.pk).exists()
    assert Limits.objects.filter(pk=target.pk).exists()
