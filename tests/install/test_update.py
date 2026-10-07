"""Exercise the real installer with isolated filesystem paths and OS commands."""

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
    (root / "etc/systemd/system").mkdir(parents=True)
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
    if [ "$1" = is-active ]; then
        [ "$SANEA_TEST_ACTIVE" -eq 1 ]
    fi
}
. "$0"
"""

    def execute(*, active: bool, from_github: bool = False, fail_install: bool = False) -> subprocess.CompletedProcess[str]:
        arguments = ["--from-github"] if from_github else []

        return subprocess.run(
            ["bash", "-c", harness, f"{INSTALLER}", "--uv", f"{fake_uv}", "--python", f"{sys.executable}", *arguments],
            env={
                **os.environ,
                "SANEA_TEST_ROOT": f"{root}",
                "SANEA_TEST_CALLS": f"{tmp_path / "calls.txt"}",
                "SANEA_TEST_UV_ARGS": f"{tmp_path / "uv-args.txt"}",
                "SANEA_TEST_ACTIVE": f"{int(active)}",
                "SANEA_TEST_FAIL": f"{int(fail_install)}",
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
        "systemctl is-active --quiet sanea.service", *stop, "uv install", "systemctl daemon-reload",
        "manage migrate --noinput", "manage collectstatic --noinput", "systemctl enable --now sanea.service",
    ]
    arguments = (tmp_path / "uv-args.txt").read_text().splitlines()
    assert arguments[-len(package_suffix):] == package_suffix
    assert arguments[arguments.index("--default-index") + 1] == "https://pypi.org/simple"
    assert (tmp_path / "root/etc/sanea/sanea.env").read_text() == "SANEA_KEEP=existing\n"
    assert (tmp_path / "root/opt/sanea/state/sanea.sqlite3").read_bytes() == b"existing statistics\n"


@pytest.mark.parametrize("active", [True, False])
def test_failed_update_restarts_only_a_previously_active_service(
    tmp_path: Path, run_installer: Callable[..., subprocess.CompletedProcess[str]], active: bool,
) -> None:
    result = run_installer(active=active, fail_install=True)

    assert result.returncode == 42
    events = (tmp_path / "calls.txt").read_text().splitlines()
    assert events == ([
        "systemctl is-active --quiet sanea.service", "systemctl stop sanea.service",
        "uv install", "systemctl start sanea.service",
    ] if active else ["systemctl is-active --quiet sanea.service", "uv install"])
