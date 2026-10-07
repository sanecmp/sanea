# sanea

sanea is the parent-facing web application.

Its Python distribution is `sanecmp-sanea`; the import package and installed
command remain `sanea`. It depends on `sanecmp-sanelib`.

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
configuration and systemd service. It runs migrations and starts the service.
Use the administrator's credentials to sign in at <http://127.0.0.1:8000/> on
the computer running sanea. That HTTP address is for local access, not remote
login over the network.

Application code lives in `/opt/sanea/bundle/sanecmp-sanea`; persistent state
is in `/opt/sanea/state` and configuration in `/etc/sanea/sanea.env`.
Management commands use the root-owned wrapper `sudo sanea` to load that
configuration and execute as the dedicated service user.

### Updating sanea

```bash
curl -fsSL https://raw.githubusercontent.com/sanecmp/sanea/main/install.sh \
    | sudo sh
```

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
