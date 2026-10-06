"""Tests for sanea installation assets."""

import subprocess
from pathlib import Path


PROJECT_ROOT = Path(__file__).parents[2]
INSTALLER = PROJECT_ROOT / "install.sh"
UNIT = PROJECT_ROOT / "systemd" / "sanea.service"


def test_installer_has_valid_shell_syntax_and_help() -> None:
    subprocess.run(["sh", "-n", f"{INSTALLER}"], check=True)

    result = subprocess.run(
        [f"{INSTALLER}", "--help"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert "--uv PATH" in result.stdout
    assert "--python PATH" in result.stdout
    assert "--index-url URL" in result.stdout
    content = INSTALLER.read_text()
    assert "raw.githubusercontent.com/sanecmp/sanea/main" in content
    assert "systemctl enable --now sanea.service" in content
    assert "sanea createsuperuser" in content


def test_systemd_unit_runs_sanea_as_dedicated_user() -> None:
    content = UNIT.read_text()

    assert "User=sanea" in content
    assert "EnvironmentFile=/etc/sanea/sanea.env" in content
    assert "ExecStart=/opt/sanea/bin/sanea serve" in content
    assert "Restart=always" in content
    assert "ReadWritePaths=/opt/sanea/state" in content
