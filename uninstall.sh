#!/bin/sh
set -eu

PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
export PATH

fail() {
    printf "uninstall.sh: %s\n" "$1" >&2
    exit 1
}

read_entry() {
    getent "$@" || {
        lookup_status=$?
        [ "$lookup_status" -eq 2 ] || fail "unable to look up $*"
    }
}

[ "$#" -eq 0 ] || fail "usage: uninstall.sh (no arguments)"
[ "$(id -u)" -eq 0 ] || fail "must run as root"

for command in systemctl getent pgrep userdel groupdel; do
    command -v "$command" >/dev/null 2>&1 || fail "required command not found: $command"
done

account_entry=$(read_entry passwd sanea)
account_uid=

if [ -n "$account_entry" ]; then
    IFS=: read -r account_name account_password account_uid account_gid account_gecos account_home account_shell <<ENTRY
$account_entry
ENTRY
    group_entry=$(read_entry group sanea)
    group_gid=$(printf "%s\n" "$group_entry" | cut -d: -f3)

    [ "$account_uid" -ne 0 ] \
        && [ "$account_home" = /opt/sanea ] \
        && [ "$account_shell" = /usr/sbin/nologin ] \
        && [ "$account_gid" = "$group_gid" ] \
        || fail "the sanea account does not match the system installation; inspect it before uninstalling"
fi

cat <<'NOTICE'
This will stop and permanently remove the local sanea installation:
  /opt/sanea (application, database, statistics and private keys)
  /etc/sanea (configuration and secret key)
  /etc/systemd/system/sanea.service
  /etc/systemd/system/multi-user.target.wants/sanea.service
  /usr/local/sbin/sanea
  The sanea OS user and its group, if the group is unused

Back up any data you want to keep. Data moved outside these paths is not removed.
NOTICE
printf "Type sanea to confirm permanent removal: " >&2
confirmation=

# Read from the terminal even when the script itself arrives through a pipe.
if ! IFS= read -r confirmation < /dev/tty || [ "$confirmation" != sanea ]; then
    printf "Uninstallation cancelled; nothing was changed.\n" >&2
    exit 0
fi

load_state=$(systemctl show --property=LoadState --value sanea.service)

if [ "$load_state" != not-found ]; then
    systemctl disable --now sanea.service
fi

if [ -n "$account_uid" ]; then
    process_status=0
    pgrep --uid "$account_uid" >/dev/null || process_status=$?

    case "$process_status" in
        0) fail "processes are still running as sanea; stop foreground sanea commands and run this script again" ;;
        1) ;;
        *) fail "unable to check for running sanea processes" ;;
    esac
fi

rm -f -- \
    /etc/systemd/system/sanea.service \
    /etc/systemd/system/multi-user.target.wants/sanea.service \
    /usr/local/sbin/sanea
systemctl daemon-reload
rm -rf -- /opt/sanea /etc/sanea

if [ -n "$account_uid" ]; then
    userdel sanea
fi

# userdel may already have removed the private group.
group_entry=$(read_entry group sanea)

if [ -n "$group_entry" ]; then
    IFS=: read -r group_name group_password group_gid group_members <<ENTRY
$group_entry
ENTRY
    passwd_entries=$(getent passwd)
    primary_members=$(printf "%s\n" "$passwd_entries" | awk -F: -v group_gid="$group_gid" '$4 == group_gid { print $1 }')

    if [ "$group_gid" -ne 0 ] && [ -z "$group_members" ] && [ -z "$primary_members" ]; then
        groupdel sanea
    else
        printf "Keeping the sanea group because it is still in use.\n" >&2
    fi
fi

printf "sanea uninstalled successfully.\n" >&2
