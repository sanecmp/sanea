"""Tests for runtime filesystem preparation."""

from pathlib import Path

import pytest

from sanea.exceptions import RuntimeSetupError
from sanea.utils.runtime import prepare_runtime_directories


def test_creates_state_and_database_directories(tmp_path: Path) -> None:
    state_dir = tmp_path / "state"
    database_dir = tmp_path / "database"

    prepare_runtime_directories(state_dir, database_dir / "sanea.sqlite3")

    assert state_dir.is_dir()
    assert database_dir.is_dir()


@pytest.mark.parametrize("blocked_directory", ["state", "database"])
def test_wraps_directory_creation_error(tmp_path: Path, blocked_directory: str) -> None:
    occupied_path = tmp_path / "occupied"
    occupied_path.write_text("not a directory")
    state_dir = occupied_path / "state" if blocked_directory == "state" else tmp_path / "state"
    database_dir = occupied_path / "database" if blocked_directory == "database" else tmp_path / "database"

    with pytest.raises(RuntimeSetupError, match="Unable to create runtime directory.*occupied") as error:
        prepare_runtime_directories(state_dir, database_dir / "sanea.sqlite3")

    assert isinstance(error.value.__cause__, OSError)
