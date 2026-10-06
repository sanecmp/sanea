#!/usr/bin/env bash

set -euo pipefail

cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
PYTHON_ENV=development uv run sanea makemessages --all --no-location --no-wrap --no-obsolete --ignore '.venv*'
