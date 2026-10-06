"""Runtime filesystem preparation."""

from pathlib import Path

from ..exceptions import RuntimeSetupError


def prepare_runtime_directories(state_dir: Path, database_path: Path) -> None:
    """Create directories required for mutable application data."""
    directories = {state_dir, database_path.parent}

    try:

        for directory in directories:
            directory.mkdir(parents=True, exist_ok=True)

    except OSError as error:
        raise RuntimeSetupError(
            f"Unable to create runtime directory '{directory}': {error}"
        ) from error
