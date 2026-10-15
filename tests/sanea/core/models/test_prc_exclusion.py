"""Tests for saving and restoring exact ignored process names."""

from collections.abc import Iterable

import pytest
from django.core.exceptions import ValidationError

from sanea.core.models import Computer, ComputerConfig, PrcExclusion


def test_ignored_process_rename_refreshes_every_computer() -> None:
    computers = [Computer.objects.create(hostname=name) for name in ("synthetic-first", "synthetic-second")]
    exclusion = PrcExclusion.create_and_materialize("demo-before")
    exclusion.prc_name = "demo-after"

    saved = exclusion.save_and_materialize()

    assert saved == exclusion

    for computer in computers:
        computer.refresh_from_db()
        names = computer.current_config.decode().ignored_prcs
        assert "demo-after" in names
        assert "demo-before" not in names


def test_adding_a_removed_process_restores_the_same_row() -> None:
    removed = PrcExclusion.objects.create(prc_name="demo-removed", apply=False)

    saved = PrcExclusion.create_and_materialize(removed.prc_name)

    assert saved.pk == removed.pk
    assert saved.apply is True
    assert PrcExclusion.objects.filter(prc_name=removed.prc_name).count() == 1


def test_renamed_packaged_process_is_not_reinstalled_under_its_old_name() -> None:
    exclusion = PrcExclusion.objects.get(prc_name="nautilus")
    exclusion.prc_name = "demo-renamed"

    exclusion.save_and_materialize()
    PrcExclusion.install_defaults()

    assert "demo-renamed" in PrcExclusion.get_names()
    assert "nautilus" not in PrcExclusion.get_names()
    assert PrcExclusion.objects.get(prc_name="nautilus").apply is False


@pytest.mark.parametrize("invalid_name", ["", "x" * 16, "nautilus"])
def test_ignored_process_rename_rejects_invalid_names(invalid_name: str) -> None:
    exclusion = PrcExclusion.objects.create(prc_name="demo-original")
    exclusion.prc_name = invalid_name

    with pytest.raises(ValidationError, match="prc_name"):
        exclusion.save_and_materialize()

    exclusion.refresh_from_db()
    assert exclusion.prc_name == "demo-original"


@pytest.mark.parametrize("existing", [False, True], ids=["add", "rename"])
def test_ignored_process_save_rolls_back_if_config_materialization_fails(
    monkeypatch: pytest.MonkeyPatch, existing: bool,
) -> None:
    computer = Computer.objects.create(hostname="synthetic-rollback")
    previous = computer.materialize_config()
    exclusion = PrcExclusion.objects.create(prc_name="demo-original") if existing else PrcExclusion()
    exclusion.prc_name = "demo-changed"
    config_count = ComputerConfig.objects.count()
    materialize = Computer.materialize_configs

    def fail_after_materializing(computer_ids: Iterable[int]) -> None:
        materialize(computer_ids)
        raise RuntimeError("synthetic materialization failure")

    monkeypatch.setattr(Computer, "materialize_configs", fail_after_materializing)

    with pytest.raises(RuntimeError, match="synthetic materialization failure"):
        exclusion.save_and_materialize()

    computer.refresh_from_db()
    assert computer.current_config == previous
    assert ComputerConfig.objects.count() == config_count
    assert not PrcExclusion.objects.filter(prc_name="demo-changed").exists()
    assert PrcExclusion.objects.filter(prc_name="demo-original").exists() is existing
