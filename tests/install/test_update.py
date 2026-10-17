"""Exercise the real installer with isolated filesystem paths and OS commands."""

import json
import os
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

import pytest


INSTALLER = Path(__file__).parents[2] / "install.sh"


@pytest.fixture
def run_installer(tmp_path: Path) -> Callable[..., subprocess.CompletedProcess[str]]:
    root = tmp_path / "root"
    config = root / "etc/sanea/sanea.env"
    config.parent.mkdir(parents=True)
    config.write_text("SANEA_KEEP=existing\n")
    state = root / "opt/sanea/state/sanea.sqlite3"
    state.parent.mkdir(parents=True)
    state.write_bytes(b"existing statistics\n")
    (root / "usr/local/sbin").mkdir(parents=True)
    unit = root / "etc/systemd/system/sanea.service"
    unit.parent.mkdir(parents=True)
    unit.write_text("existing service\n")
    fake_uv = tmp_path / "uv"
    fake_uv.write_text("""#!/bin/sh
set -eu
printf '%s\\n' 'uv install' >> "$SANEA_TEST_CALLS"
printf '%s\\n' "$@" > "$SANEA_TEST_UV_ARGS"
[ "$SANEA_TEST_FAIL" -eq 0 ] || exit 42
mkdir -p "$UV_TOOL_DIR" "$UV_TOOL_BIN_DIR"
printf '#!/bin/sh\\nexit 0\\n' > "$UV_TOOL_BIN_DIR/sanea"
chmod 0755 "$UV_TOOL_BIN_DIR/sanea"
""")
    fake_uv.chmod(0o755)
    # Functions mock privileged OS interactions without changing the installer.
    # Every write is redirected into tmp_path before the first filesystem action.
    harness = """
id() { printf '0\\n'; }
stat() {
    case "$2" in
        %u) printf '0\\n' ;;
        %a) printf '755\\n' ;;
    esac
}
getent() {
    app_dir="$SANEA_TEST_ROOT/opt/sanea"
    state_dir="$app_dir/state"
    bundle_dir="$app_dir/bundle"
    bin_dir="$app_dir/bin"
    config_dir="$SANEA_TEST_ROOT/etc/sanea"
    config_path="$config_dir/sanea.env"
    unit_target="$SANEA_TEST_ROOT/etc/systemd/system/sanea.service"
    wrapper_target="$SANEA_TEST_ROOT/usr/local/sbin/sanea"
}
install() {
    local arguments=()
    while [ "$#" -gt 0 ]; do
        case "$1" in
            -o|-g) shift 2 ;;
            *) arguments+=("$1"); shift ;;
        esac
    done
    local destination="${arguments[-1]}"
    [[ "$destination" == "$SANEA_TEST_ROOT/"* ]] || return 99
    if [ "$destination" = "$wrapper_target" ]; then
        printf '#!/bin/sh\\nprintf "manage %%s\\\\n" "$*" >> "$SANEA_TEST_CALLS"\\n' > "$destination"
        chmod 0755 "$destination"
    else
        command install "${arguments[@]}"
    fi
}
systemctl() {
    printf 'systemctl %s\\n' "$*" >> "$SANEA_TEST_CALLS"
    case "$1" in
        is-active) [ "$SANEA_TEST_ACTIVE" -eq 1 ] ;;
        is-enabled) [ "$SANEA_TEST_ENABLED" -eq 1 ] ;;
    esac
}
hostname() {
    if [ "$#" -eq 0 ]; then
        printf 'sanea-box\\n'
    else
        [ "$1" = -I ] || return 99
        [ "$SANEA_TEST_ADDRESS_FAILURE" -eq 0 ] || return 1
        printf '%s\\n' "$SANEA_TEST_ADDRESSES"
    fi
}
. "$0"
"""

    def execute(
        *, active: bool, from_github: bool = False, fail_install: bool = False,
        existing_config: bool = True, addresses: str = "192.168.1.10", address_failure: bool = False,
        existing_unit: bool = True, enabled: bool = True, no_autostart: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        arguments = ["--from-github"] if from_github else []

        if no_autostart:
            arguments.append("--no-autostart")

        if not existing_config:
            config.unlink()

        if not existing_unit:
            unit.unlink()

        return subprocess.run(
            ["bash", "-c", harness, f"{INSTALLER}", "--uv", f"{fake_uv}", "--python", f"{sys.executable}", *arguments],
            env={
                **os.environ,
                "SANEA_TEST_ROOT": f"{root}",
                "SANEA_TEST_CALLS": f"{tmp_path / "calls.txt"}",
                "SANEA_TEST_UV_ARGS": f"{tmp_path / "uv-args.txt"}",
                "SANEA_TEST_ACTIVE": f"{int(active)}",
                "SANEA_TEST_ENABLED": f"{int(enabled)}",
                "SANEA_TEST_FAIL": f"{int(fail_install)}",
                "SANEA_TEST_ADDRESSES": addresses,
                "SANEA_TEST_ADDRESS_FAILURE": f"{int(address_failure)}",
            },
            capture_output=True, text=True,
        )

    return execute


@pytest.mark.parametrize("active", [True, False])
@pytest.mark.parametrize(("from_github", "package_suffix"), [
    pytest.param(False, ["sanecmp-sanea"], id="pypi"),
    pytest.param(True, [
        "--with", "sanecmp-sanelib @ git+https://github.com/sanecmp/sanelib.git@main",
        "sanecmp-sanea @ git+https://github.com/sanecmp/sanea.git@main",
    ], id="github-main"),
])
def test_update_preserves_data_and_restarts_service_after_migrations(
    tmp_path: Path, run_installer: Callable[..., subprocess.CompletedProcess[str]],
    active: bool, from_github: bool, package_suffix: list[str],
) -> None:
    result = run_installer(active=active, from_github=from_github)

    assert result.returncode == 0, result.stderr
    events = (tmp_path / "calls.txt").read_text().splitlines()
    stop = ["systemctl stop sanea.service"] if active else []
    assert events == [
        "systemctl is-enabled --quiet sanea.service", "systemctl is-active --quiet sanea.service",
        *stop, "uv install", "systemctl daemon-reload",
        "manage migrate --noinput", "manage collectstatic --noinput", "systemctl enable --now sanea.service",
    ]
    arguments = (tmp_path / "uv-args.txt").read_text().splitlines()
    assert arguments[-len(package_suffix):] == package_suffix
    assert arguments[arguments.index("--default-index") + 1] == "https://pypi.org/simple"
    assert (tmp_path / "root/etc/sanea/sanea.env").read_text() == "SANEA_KEEP=existing\n"
    assert (tmp_path / "root/opt/sanea/state/sanea.sqlite3").read_bytes() == b"existing statistics\n"


@pytest.mark.parametrize("active", [True, False])
@pytest.mark.parametrize("no_autostart", [True, False])
def test_failed_update_restarts_only_a_previously_active_service(
    tmp_path: Path, run_installer: Callable[..., subprocess.CompletedProcess[str]], active: bool, no_autostart: bool,
) -> None:
    result = run_installer(active=active, fail_install=True, no_autostart=no_autostart)

    assert result.returncode == 42
    events = (tmp_path / "calls.txt").read_text().splitlines()
    check_enabled = [] if no_autostart else ["systemctl is-enabled --quiet sanea.service"]
    stop = ["systemctl stop sanea.service"] if active else []
    restart = ["systemctl start sanea.service"] if active else []
    assert events == [
        *check_enabled, "systemctl is-active --quiet sanea.service", *stop, "uv install", *restart,
    ]


@pytest.mark.parametrize(("existing_unit", "active"), [
    pytest.param(False, False, id="first-installation"),
    pytest.param(True, False, id="stopped-service"),
    pytest.param(True, True, id="running-service"),
])
def test_no_autostart_leaves_service_installed_stopped_and_disabled(
    tmp_path: Path, run_installer: Callable[..., subprocess.CompletedProcess[str]], existing_unit: bool, active: bool,
) -> None:
    result = run_installer(
        active=active, existing_unit=existing_unit, existing_config=existing_unit, no_autostart=True,
    )

    assert result.returncode == 0, result.stderr
    stop = ["systemctl stop sanea.service"] if active else []
    assert (tmp_path / "calls.txt").read_text().splitlines() == [
        "systemctl is-active --quiet sanea.service", *stop, "uv install", "systemctl daemon-reload",
        "manage migrate --noinput", "manage collectstatic --noinput", "systemctl disable sanea.service",
    ]
    assert "Start manually with: sudo sanea serve" in result.stdout
    assert "Service autostart is disabled." in result.stdout
    assert "installed and started" not in result.stdout
    assert "ExecStart=/opt/sanea/bin/sanea serve" in (tmp_path / "root/etc/systemd/system/sanea.service").read_text()
    assert (tmp_path / "root/usr/local/sbin/sanea").is_file()
    assert (tmp_path / "root/etc/sanea/sanea.env").is_file()
    assert (tmp_path / "root/opt/sanea/state/sanea.sqlite3").read_bytes() == b"existing statistics\n"


@pytest.mark.parametrize("active", [True, False])
def test_update_preserves_disabled_autostart_and_previous_running_state(
    tmp_path: Path, run_installer: Callable[..., subprocess.CompletedProcess[str]], active: bool,
) -> None:
    result = run_installer(active=active, enabled=False)

    assert result.returncode == 0, result.stderr
    stop = ["systemctl stop sanea.service"] if active else []
    restart = ["systemctl start sanea.service"] if active else []
    assert (tmp_path / "calls.txt").read_text().splitlines() == [
        "systemctl is-enabled --quiet sanea.service", "systemctl is-active --quiet sanea.service",
        *stop, "uv install", "systemctl daemon-reload",
        "manage migrate --noinput", "manage collectstatic --noinput", *restart,
    ]
    assert "Service autostart is disabled." in result.stdout
    assert ("Start manually with: sudo sanea serve" in result.stdout) == (not active)
    assert (tmp_path / "root/etc/sanea/sanea.env").read_text() == "SANEA_KEEP=existing\n"
    assert (tmp_path / "root/opt/sanea/state/sanea.sqlite3").read_bytes() == b"existing statistics\n"


@pytest.mark.parametrize(("addresses", "expected"), [
    pytest.param(
        "192.168.1.10 10.0.0.2 192.168.1.10 2001:db8::2 fe80::1 0.0.0.0 :: 224.0.0.1 ff02::1",
        ["192.168.1.10", "10.0.0.2", "[2001:db8::2]"], id="local-addresses",
    ),
    pytest.param("", [], id="no-network"),
])
def test_first_installation_configures_local_hosts_without_wildcard(
    tmp_path: Path, run_installer: Callable[..., subprocess.CompletedProcess[str]], addresses: str, expected: list[str],
) -> None:
    result = run_installer(active=False, existing_config=False, existing_unit=False, addresses=addresses)

    assert result.returncode == 0, result.stderr
    config = (tmp_path / "root/etc/sanea/sanea.env").read_text()
    line = next(line for line in config.splitlines() if line.startswith("SANEA_ALLOWED_HOSTS="))
    hosts = json.loads(line.split("=", 1)[1].strip("'"))
    assert hosts == ["localhost", "127.0.0.1", "[::1]", "sanea", "sanea-box", *expected]
    assert "*" not in hosts
    assert (tmp_path / "calls.txt").read_text().splitlines()[-1] == "systemctl enable --now sanea.service"
    assert "installed and started successfully" in result.stdout
    assert (tmp_path / "root/opt/sanea/state/sanea.sqlite3").read_bytes() == b"existing statistics\n"


@pytest.mark.parametrize(("addresses", "address_failure", "message"), [
    pytest.param("not-an-address", False, "unable to prepare allowed hosts", id="invalid-address"),
    pytest.param("", True, "unable to list local IP addresses", id="lookup-error"),
])
def test_address_detection_failure_does_not_write_config_and_restarts_previous_service(
    tmp_path: Path, run_installer: Callable[..., subprocess.CompletedProcess[str]],
    addresses: str, address_failure: bool, message: str,
) -> None:
    result = run_installer(active=True, existing_config=False, addresses=addresses, address_failure=address_failure)

    assert result.returncode == 1
    assert message in result.stderr
    assert not (tmp_path / "root/etc/sanea/sanea.env").exists()
    assert (tmp_path / "calls.txt").read_text().splitlines()[-1] == "systemctl start sanea.service"
    assert (tmp_path / "root/opt/sanea/state/sanea.sqlite3").read_bytes() == b"existing statistics\n"


def test_update_preserves_custom_hosts_without_network_detection(
    tmp_path: Path, run_installer: Callable[..., subprocess.CompletedProcess[str]],
) -> None:
    config = tmp_path / "root/etc/sanea/sanea.env"
    existing = "SANEA_ALLOWED_HOSTS='[\"sanea.home\",\"192.168.1.20\"]'\n"
    config.write_text(existing)

    result = run_installer(active=True, addresses="not-an-address", address_failure=True)

    assert result.returncode == 0, result.stderr
    assert config.read_text() == existing
