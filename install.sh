#!/bin/sh
set -eu

PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
export PATH

usage() {
    cat <<'USAGE'
Usage: install.sh [--uv PATH] [--python PATH] [--index-url URL] [PACKAGE]
                  [--from-github]

Install sanea as a system service. PACKAGE defaults to "sanecmp-sanea" and may be an
exact requirement or a local wheel path.
--from-github installs sanea and sanelib from the main branches of their GitHub
repositories and requires git. PACKAGE cannot be combined with this mode.
USAGE
}

fail() {
    printf 'install.sh: %s\n' "$1" >&2
    exit 1
}

validate_directory_chain() {
    directory=$(dirname -- "$1")
    while :; do
        [ "$(stat -c %u "$directory")" -eq 0 ] \
            || fail "directory is not owned by root: $directory"
        mode=$(stat -c %a "$directory")
        [ $((0$mode & 022)) -eq 0 ] \
            || fail "directory is writable by group or others: $directory"
        [ "$directory" = / ] && break
        directory=$(dirname -- "$directory")
    done
}

resolve_executable() {
    value=$1
    case "$value" in
        */*) candidate=$value ;;
        *) candidate=$(command -v "$value" 2>/dev/null || true) ;;
    esac
    [ -n "$candidate" ] || fail "executable not found: $value"
    candidate=$(readlink -f "$candidate")
    [ -x "$candidate" ] || fail "not executable: $candidate"
    [ "$(stat -c %u "$candidate")" -eq 0 ] || fail "not owned by root: $candidate"
    mode=$(stat -c %a "$candidate")
    [ $((0$mode & 022)) -eq 0 ] || fail "writable by group or others: $candidate"
    validate_directory_chain "$candidate"
    printf '%s\n' "$candidate"
}

uv_command=uv
python_command=/usr/bin/python3
index_url=https://pypi.org/simple
package=sanecmp-sanea
package_set=0
from_github=0

while [ "$#" -gt 0 ]; do
    case "$1" in
        --uv)
            [ "$#" -ge 2 ] || fail "--uv requires a path"
            uv_command=$2
            shift 2
            ;;
        --python)
            [ "$#" -ge 2 ] || fail "--python requires a path"
            python_command=$2
            shift 2
            ;;
        --index-url)
            [ "$#" -ge 2 ] || fail "--index-url requires a URL"
            index_url=$2
            shift 2
            ;;
        --from-github)
            from_github=1
            shift
            ;;
        --help|-h)
            usage
            exit 0
            ;;
        --*)
            fail "unknown option: $1"
            ;;
        *)
            [ "$package_set" -eq 0 ] || fail "only one PACKAGE may be specified"
            package=$1
            package_set=1
            shift
            ;;
    esac
done

if [ "$from_github" -eq 1 ]; then
    [ "$package_set" -eq 0 ] || fail "PACKAGE cannot be combined with --from-github"
    command -v git >/dev/null 2>&1 || fail "git is required for --from-github"
    package="sanecmp-sanea @ git+https://github.com/sanecmp/sanea.git@main"
    set -- --with "sanecmp-sanelib @ git+https://github.com/sanecmp/sanelib.git@main"
else
    set --
fi

[ "$(id -u)" -eq 0 ] || fail "must run as root"
case "$index_url" in
    https://*) ;;
    *) fail "index URL must use HTTPS" ;;
esac
case "${index_url#https://}" in
    ''|*@*|*\#*) fail "index URL must not contain credentials or a fragment" ;;
esac
case "$index_url" in
    *[[:space:]]*) fail "index URL must not contain whitespace" ;;
esac
case "$package" in
    -*) fail "PACKAGE must not start with a hyphen" ;;
esac

uv_path=$(resolve_executable "$uv_command")
python_path=$(resolve_executable "$python_command")
"$python_path" -c 'import sys; raise SystemExit(sys.version_info < (3, 12))' \
    || fail "Python 3.12 or newer is required"

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
unit_source=$script_dir/systemd/sanea.service
asset_tmp_dir=
if [ ! -f "$unit_source" ]; then
    command -v curl >/dev/null 2>&1 || fail "curl is required for remote installation"
    asset_tmp_dir=$(mktemp -d)
    curl -fsSL \
        https://raw.githubusercontent.com/sanecmp/sanea/main/systemd/sanea.service \
        -o "$asset_tmp_dir/sanea.service" \
        || fail "unable to download sanea.service"
    unit_source=$asset_tmp_dir/sanea.service
fi

app_dir=/opt/sanea
state_dir=$app_dir/state
bundle_dir=$app_dir/bundle
bin_dir=$app_dir/bin
config_dir=/etc/sanea
config_path=$config_dir/sanea.env
unit_target=/etc/systemd/system/sanea.service
wrapper_target=/usr/local/sbin/sanea
was_active=0

cleanup() {
    if [ "$was_active" -eq 1 ]; then
        systemctl start sanea.service || true
    fi
    if [ -n "$asset_tmp_dir" ]; then
        rm -rf "$asset_tmp_dir"
    fi
}
trap cleanup EXIT

if ! getent group sanea >/dev/null 2>&1; then
    groupadd --system sanea
fi
if ! getent passwd sanea >/dev/null 2>&1; then
    useradd --system --gid sanea --home-dir "$app_dir" --shell /usr/sbin/nologin sanea
fi

install -d -o root -g root -m 0755 "$app_dir" "$bundle_dir" "$bin_dir"
install -d -o sanea -g sanea -m 0700 "$state_dir"
install -d -o root -g sanea -m 0750 "$config_dir"

if systemctl is-active --quiet sanea.service; then
    was_active=1
    systemctl stop sanea.service
fi

for variable in $(env | sed -n 's/^\(UV_[A-Za-z0-9_]*\)=.*/\1/p'); do
    unset "$variable"
done

UV_TOOL_DIR=$bundle_dir \
UV_TOOL_BIN_DIR=$bin_dir \
"$uv_path" tool install \
    --force \
    --no-cache \
    --no-config \
    --no-sources \
    --no-managed-python \
    --no-python-downloads \
    --no-progress \
    --color never \
    --index-strategy first-index \
    --default-index "$index_url" \
    --python "$python_path" \
    "$@" \
    "$package"

[ -x "$bin_dir/sanea" ] || fail "uv did not install the sanea entry point"

if [ ! -f "$config_path" ]; then
    secret=$("$python_path" -c 'import secrets; print(secrets.token_urlsafe(48))')
    host_name=$(hostname 2>/dev/null || printf localhost)
    config_tmp=$(mktemp "$config_dir/.sanea.env.XXXXXX")
    cat > "$config_tmp" <<CONFIG
PYTHON_ENV=production
SANEA_SECRET_KEY=$secret
SANEA_STATE_DIR=$state_dir
SANEA_DATABASE_PATH=$state_dir/sanea.sqlite3
SANEA_ALLOWED_HOSTS='["localhost","127.0.0.1","[::1]","$host_name"]'
SANEA_SERVER_HOST=0.0.0.0
SANEA_HTTP_PORT=8000
SANEA_HTTPS_PORT=8443
SANEA_DISCOVERY_PORT=62117
SANEA_PKI_DIR=$state_dir/pki
CONFIG
    install -o root -g sanea -m 0640 "$config_tmp" "$config_path"
    rm -f "$config_tmp"
fi

wrapper_tmp=$(mktemp "$config_dir/.sanea-wrapper.XXXXXX")
cat > "$wrapper_tmp" <<'WRAPPER'
#!/bin/sh
set -eu
set -a
. /etc/sanea/sanea.env
set +a
exec runuser --preserve-environment -u sanea -- /opt/sanea/bin/sanea "$@"
WRAPPER
install -o root -g root -m 0755 "$wrapper_tmp" "$wrapper_target"
rm -f "$wrapper_tmp"

install -o root -g root -m 0644 "$unit_source" "$unit_target"
systemctl daemon-reload
"$wrapper_target" migrate --noinput
"$wrapper_target" collectstatic --noinput
systemctl enable --now sanea.service
was_active=0

trap - EXIT
cleanup

printf '%s\n' 'sanea installed and started successfully.'
printf '%s\n' 'Create the first administrator with: sudo sanea createsuperuser'
printf 'Open: https://%s:8443/\n' "$(hostname 2>/dev/null || printf localhost)"
