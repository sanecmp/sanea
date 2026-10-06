"""Shared sanea data fixtures."""

import json
from pathlib import Path
from typing import Any

import pytest


@pytest.fixture
def settings_payload(datafix_dir: Path) -> dict[str, Any]:
    """Load representative testing settings defaults."""
    return json.loads((datafix_dir / "settings.json").read_text())
