# sanea

sanea is the parent-facing web application.

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
