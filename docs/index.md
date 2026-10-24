# sanea guide

sanea is the parent-facing web application.

Its Python distribution is `sanecmp-sanea`; the import package and installed
command remain `sanea`. It depends on `sanecmp-sanelib`.

## Requirements

Python 3.12+ and uv. System installation requires Linux with systemd, curl and protected system executables.
Local development uses makeapp (`makeapp>=2.3,<3`); browser-script tests additionally need Node.js 18+.

## Installation

Run the installer described under [System installation](#system-installation), then create an administrator account.
Use the local development commands below for an editable checkout.

## Local development

Run these commands from the `sanea/` package directory:

```bash
ma tools
ma up --tool
ma tests
```

`ma tools` prepares development tools, `ma up --tool` installs the editable CLI,
and `ma tests` runs the configured Python 3.12 test matrix. Run installed management
commands directly as `sanea`; no separate environment activation is needed.
CI continues to run pytest directly, without makeapp.

Browser-script unit tests use Node.js 18+ without additional packages:

```bash
node --test tests/javascript/*.mjs
```

## Browser interface

**Dashboard** shows screen time by person across their computers and the 10 most
used applications. Both charts share period and person filters: the last 24 hours,
48 hours (default), 7 days or 30 days, a calendar day, and all people or one person selected by name.
Short periods use hourly bars; 7 and 30 days use 24-hour bars.
It refreshes every minute while visible, retaining the selected filters.
Usage within chart intervals and runs crossing the window boundary are estimated by
distributing each final duration proportionally over its start-to-end interval.
Simultaneous activity on different accounts or in different applications is added
together, not deduplicated.

**Statistics**, the next navigation item, shows activity charts, recent activity
and the top 10 applications by recorded usage time, with user, computer, account
and period filters. Choose today, the last 7 or 30 days, or a specific day in the
calendar. **Period** opens a single calendar with shortcuts for today, the last
7 days and the last 30 days; choosing a date selects that day instead.
The calendar uses the bundled Flatpickr 4.6.13, including Russian labels; no CDN
is needed. Without JavaScript, the same field selects a day using the browser's
native date input.

Recent applications and sessions have separate tabs, ordered by completion time.
Applications group all completed launches in the selected period by application
ID, or by process name and executable when the ID is unknown. Each of the 10 most
recent applications shows its total duration, launch count and accounts.
The sessions tab shows up to 10 completed sessions, including those that started
before the selected period. Changing filters keeps the selected tab.

Time totals include only completed sessions and application runs. A dash in
application usage means no final duration has been received yet.
Usage totals are assigned to the local start date; recent activity uses the local
completion date. GNOME Shell, Mutter's X11 window frames and the recognized DING
desktop-icons extension are omitted from application reports and dashboard charts.
Their original events remain stored, and excluding them does not reduce session
screen time. Other GJS scripts are not hidden just because they use GJS.
Dates and times use sanea's timezone, including the days selected in statistics.
Tables use the `YYYY-MM-DD HH:MM` format and regular-weight values; headings remain bold.
By default this is the system timezone of the computer running sanea;
`SANEA_TIME_ZONE` overrides it with an IANA name such as `Europe/Berlin`.
UTC is used if no valid system timezone name is available.
Children's schedule timezones remain configured separately for each computer.

**Computers** lists registered computers. Its information button opens details in a
dialog; choose **Edit** there to change settings. Closing the dialog discards unsaved
changes. Registration expands above the table. Command history and sanex updates
have separate pages with breadcrumbs back to the list.
While visible, the list and command history refresh every five seconds. Unchanged
tables stay in place; changed rows keep the table's scroll position. Refreshing
pauses while computer details or settings are open.

Issues and diagnostic logs appear below the computer list, with their own computer
and period filters. The dashboard, statistics and issues reuse the same **Period**
calendar with report-specific shortcuts and local calendar-day selection. Diagnostic
logs are the latest snapshots, not a historical archive: a day filters their receipt dates.
Logs only refresh when **Refresh** is clicked. Use the copy
icon to copy the displayed log text.

**People** adds and renames people in a dialog. A person's template links to its
settings in **Limits**. Choose the template's default recipients there; saving
does not change existing account limits.

**Limits** adds and edits templates in the same dialog. Each row lists the people
using the template and the accounts with its latest version, alongside that
version's session-rule and schedule-range counts. The **Distribute template** icon
opens a warning and the recipient list; only confirming the selected accounts
replaces their limits with the latest template version.

Schedule ranges are added and edited in a dialog. The **In schedule** icon shows
whether an interval is included in the saved schedule, not whether it is active now.

Session rules use the same add and edit dialog, with session count, duration and
break duration in one row. The **Limits** icon shows whether the rule's session
quotas and nested application rules are applied.

Application rules also use a dialog. Quotas share a row; each recognition condition
shares a row with its matching method. Process-name and executable-path suggestions
remain available. The **Applied** icon reflects the rule's **Apply limits** checkbox,
which appears first on its own row.

The account limits editor reuses the forms and layouts for session rules, schedule
ranges and application rules. It adds session selection and row removal, and shows
durations in minutes instead of seconds.

Ignored processes appear below the templates. The add button and edit icons open
the same dialog. Removing a process takes it off the list; adding the same name restores it.

## Development server

```bash
./develop.sh
```

This installs the CLI through `ma up --tool`, prepares the database, creates or
updates the `demo` / `demo` staff user, and starts Django with automatic reloading.
To use the production-like Cheroot TLS server instead:

```bash
./develop.sh --tls
```

Development and testing defaults are defined in the Python settings.
See `.env.example` for available overrides. Actual `.env` files are local and
untracked; keep production credentials in `.env.production`. Never use the public
development or testing secret keys in production.

## Common commands

```bash
PYTHON_ENV=development sanea migrate
PYTHON_ENV=development sanea check
ma tests
./localize.sh
uv build
```

Do not create additional migrations during current development. After model
changes, remove the old `0001_initial.py` and regenerate it with
`PYTHON_ENV=development sanea makemigrations core`. Formatting alone must not
regenerate the migration.

Build release wheel and sdist files with `uv build`. Production installation
continues to use the existing uv-based installer, not makeapp.

## System installation

The installer requires curl, a system Python 3.12+ and a system uv. Python, uv
and their containing directories must be owned by root and not writable by
unprivileged users. uv's user-local installation is not sufficient. By default,
the installer uses `/usr/bin/python3` and searches the system PATH for uv;
`--python` and `--uv` select other protected absolute paths.

Run the installer as root:

```bash
curl -fsSL https://raw.githubusercontent.com/sanecmp/sanea/main/install.sh \
    | sudo sh -s -- 'sanecmp-sanea==0.1.0'
sudo sanea createsuperuser
```

PyPI is the default source. To install from GitHub instead, pass `--from-github`
after `sudo sh -s --`; this mode requires system Git and installs both sanea
and sanelib from the `main` branches of their official repositories.
Do not supply `PACKAGE` together with `--from-github`. Third-party dependencies
still come from PyPI, or the HTTPS index selected with `--index-url`.

The installer creates the dedicated `sanea` OS user, database, random secret,
configuration and systemd service. It runs migrations and, by default, starts
the service and enables startup at boot.
It also collects static assets, which the embedded server serves through
WhiteNoise without a separate web server.
Use the administrator's credentials to sign in at <http://127.0.0.1:8000/> on
the computer running sanea. That HTTP address is for local access, not remote
login over the network.

Application code lives in `/opt/sanea/bundle/sanecmp-sanea`; persistent state
is in `/opt/sanea/state` and configuration in `/etc/sanea/sanea.env`.
The installer adds `/usr/local/sbin/sanea`. Management commands use this root-owned
wrapper as `sudo sanea` to load the configuration and execute as the dedicated service user.

### Manual startup

To run sanea only when needed, install it with `--no-autostart`:

```bash
curl -fsSL https://raw.githubusercontent.com/sanecmp/sanea/main/install.sh \
    | sudo sh -s -- --no-autostart 'sanecmp-sanea==0.1.0'
sudo sanea createsuperuser
sudo sanea serve
```

Files and permissions stay the same, so installation and startup still require
`sudo`. The systemd unit remains installed, but the service is stopped and disabled,
including when applying this option to an existing installation. The foreground
server runs until you press `Ctrl+C`; open its interface in the browser as usual.
Do not run it alongside the systemd service.

To enable service autostart later, stop the foreground server first, then run:

```bash
sudo systemctl enable --now sanea.service
```

### Updating sanea

Stop any foreground `sanea serve` process before updating:

```bash
curl -fsSL https://raw.githubusercontent.com/sanecmp/sanea/main/install.sh \
    | sudo sh
```

Updates preserve the service's enabled or disabled autostart state. A disabled
service is restarted only if it was already running; `--no-autostart` always
leaves it stopped and disabled. After a manual installation, run `sudo sanea serve`
again when needed; there is no need to repeat `--no-autostart` on each update.

### Home-network access

On first installation, the installer fills `SANEA_ALLOWED_HOSTS` with loopback
addresses, `sanea`, the OS hostname and local IPv4/IPv6 addresses. It reads the
addresses from local interfaces with `hostname -I`, without an external lookup
or a wildcard. Existing configuration is preserved during updates.

If sanea's IP address changes or you need another DNS name, edit
`/etc/sanea/sanea.env` as root and update `SANEA_ALLOWED_HOSTS`.
For browser HTTPS access from another computer, make the DNS name `sanea`
resolve to sanea's IP through your home DNS or the browsing computer's hosts file.

After changing the configuration:

```bash
sudo systemctl restart sanea.service
```

For manual startup, stop the foreground server and run `sudo sanea serve` again instead.

Allow inbound TCP 8443 and UDP 62117 from your home network. UDP discovery
requires the devices to share a reachable local broadcast network; guest-network
isolation can prevent registration. Do not expose these listeners to the internet.

For browser access, trust the public CA certificate
`/opt/sanea/state/pki/ca.crt` in the browser and open <https://sanea:8443/>.
The generated server certificate currently covers `sanea` and `localhost`,
not arbitrary IP addresses or machine names. Trusting the CA alone does not
make a different hostname valid. Never copy the private `.key` files.

In **Computers**, open registration and run the displayed command on the
child's computer within 30 seconds. Monitoring and limits stay disabled until
you enable them for the intended local accounts.

## Recognized applications

Statistics prefer the application name supplied by sanex and aggregate by its
application ID. Technical process names and executable paths remain stored;
unknown applications use those fields as before. Different GJS scripts and
recognized Steam games therefore do not become a single interpreter or Steam
entry. Separate launches still count separately.
Sanex supplements AT-SPI with EWMH for X11/Xwayland windows and, after detecting
Steam, process-lifetime observations using its game ID hints. Native Wayland
windows without accessibility still require usable process metadata. A Steam
client entry alone does not identify which game was played; old entries cannot
be retrospectively split into games. Game names use window titles when available,
otherwise a Steam ID, without reading Steam installation files.

Search by name and select an application in the **Application** list when editing a rule.
The list comes from recorded activity for the selected accounts; the application
ID is saved automatically, without copying or entering it manually. Applications
appear after sanex recognizes them and synchronizes with sanea. Leave **Not selected**
to use only the other recognition conditions. An already selected ID remains in
the editor even when it is absent from recent activity. Additional recognition
conditions are combined using AND.
Past events without application metadata retain their original names.

The **Ignored processes** name field offers up to 50 recent process names from
recorded activity across all computers. Search the list or enter an exact name
manually. Already ignored names are omitted; matching remains case-sensitive
and limited to 15 characters. These are technical process names, not application
display names. Searching is local and sends no requests while typing.
