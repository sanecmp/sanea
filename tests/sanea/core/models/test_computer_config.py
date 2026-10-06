"""Tests for compiling and materializing sanex configurations."""

from typing import Any

from sanea.core.models import Account, Computer, ComputerConfig, PrcExclusion
from sanea.core.models.prc_exclusion import DEFAULT_IGNORED_PRCS


def test_builds_exact_sanex_payload(
    limits_snapshot_graph: dict[str, Any],
    limits_snapshot_payload: dict[str, Any],
) -> None:
    config = limits_snapshot_graph["computer"].build_client_config(ident=1842)

    assert config.model_dump(mode="json") == limits_snapshot_payload["expected_config"]


def test_includes_unmonitored_accounts_without_limits(
    limits_snapshot_graph: dict[str, Any],
) -> None:
    computer = limits_snapshot_graph["computer"]
    Account.objects.create(
        computer=computer,
        uid=1000,
        login="parent",
        name="Parent",
    )

    config = computer.build_client_config(ident=1)

    assert [account.uid for account in config.accounts] == [1000, 1001]
    assert config.accounts[0].model_dump(mode="json") == {
        "uid": 1000,
        "collect": False,
        "apply": False,
        "limits": None,
    }


def test_includes_ignored_process_names_in_stable_order(
    limits_snapshot_graph: dict[str, Any],
) -> None:
    PrcExclusion.objects.create(prc_name="zeitgeist")
    PrcExclusion.objects.create(prc_name="baobab")

    config = limits_snapshot_graph["computer"].build_client_config(ident=1)

    assert config.ignored_prcs == tuple(
        sorted((*DEFAULT_IGNORED_PRCS, "baobab", "zeitgeist"))
    )


def test_keeps_disabled_packaged_default_disabled() -> None:
    exclusion = PrcExclusion.objects.get(prc_name="nautilus")

    exclusion.delete_and_materialize()
    PrcExclusion.install_defaults()
    exclusion.refresh_from_db()

    assert exclusion.apply is False
    assert "nautilus" not in PrcExclusion.get_names()


def test_exclusion_changes_materialize_every_computer_config(
    limits_snapshot_graph: dict[str, Any],
) -> None:
    first = limits_snapshot_graph["computer"]
    second = Computer.objects.create(hostname="second")
    initial = (first.materialize_config(), second.materialize_config())

    exclusion = PrcExclusion.create_and_materialize("xmessage")
    first.refresh_from_db()
    second.refresh_from_db()

    assert first.current_config != initial[0]
    assert second.current_config != initial[1]
    assert first.current_config.decode().ignored_prcs == tuple(
        sorted((*DEFAULT_IGNORED_PRCS, "xmessage"))
    )
    assert second.current_config.decode().ignored_prcs == tuple(
        sorted((*DEFAULT_IGNORED_PRCS, "xmessage"))
    )

    exclusion.delete_and_materialize()
    first.refresh_from_db()
    second.refresh_from_db()

    assert first.current_config.decode().ignored_prcs == tuple(DEFAULT_IGNORED_PRCS)
    assert second.current_config.decode().ignored_prcs == tuple(DEFAULT_IGNORED_PRCS)


def test_materialization_reuses_identical_ready_payload(
    limits_snapshot_graph: dict[str, Any],
) -> None:
    computer = limits_snapshot_graph["computer"]

    first = computer.materialize_config()
    second = computer.materialize_config()
    computer.refresh_from_db()

    assert second == first
    assert ComputerConfig.objects.count() == 1
    assert computer.current_config == first
    assert first.decode().ident == first.ident


def test_materialization_creates_new_config_only_for_transmitted_changes(
    limits_snapshot_graph: dict[str, Any],
) -> None:
    computer = limits_snapshot_graph["computer"]
    account = limits_snapshot_graph["account"]
    first = computer.materialize_config()
    original_payload = bytes(first.payload)

    account.login = "renamed"
    account.save(update_fields=("login", "updated"))
    unchanged = computer.materialize_config()

    account.collect = False
    account.save(update_fields=("collect", "updated"))
    changed = computer.materialize_config()
    computer.refresh_from_db()

    assert unchanged == first
    assert changed.ident != first.ident
    assert changed.decode().accounts[0].collect is False
    assert bytes(ComputerConfig.objects.get(pk=first.pk).payload) == original_payload
    assert computer.current_config == changed


def test_acknowledgement_keeps_only_current_and_applied_configs(
    limits_snapshot_graph: dict[str, Any],
) -> None:
    computer = limits_snapshot_graph["computer"]
    account = limits_snapshot_graph["account"]
    first = computer.materialize_config()
    account.collect = False
    account.save(update_fields=("collect", "updated"))
    second = computer.materialize_config()
    account.collect = True
    account.save(update_fields=("collect", "updated"))
    third = computer.materialize_config()
    computer.refresh_from_db()

    computer.acknowledge_config(second.ident)

    assert set(computer.configs.values_list("ident", flat=True)) == {
        second.ident,
        third.ident,
    }
    computer.acknowledge_config(third.ident)
    assert list(computer.configs.values_list("ident", flat=True)) == [third.ident]
    assert not ComputerConfig.objects.filter(pk=first.ident).exists()
