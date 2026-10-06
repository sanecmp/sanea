#!/usr/bin/env bash

set -euo pipefail

cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
export PYTHON_ENV=development

server_command=(runserver)
if [[ "${1:-}" == "--tls" ]]; then
    server_command=(serve)
    shift
elif [[ "${1:-}" == "--help" ]]; then
    cat <<'EOF'
Usage:
  ./develop.sh [runserver arguments]
  ./develop.sh --tls [serve arguments]

The default mode uses Django runserver with automatic source reloading.
The --tls mode uses Cheroot with the same TLS and client-certificate handling
as an installed sanea instance.
EOF
    exit 0
fi

ma up --tool
sanea migrate --noinput
sanea shell <<'PY'
from django.contrib.auth import get_user_model


user_model = get_user_model()
user, created = user_model.objects.get_or_create(username="demo")
user.is_active = True
user.is_staff = True
user.set_password("demo")
user.save(update_fields=["is_active", "is_staff", "password"])

state = "created" if created else "updated"
print(f"Development user demo was {state}.")
PY

printf '\nDevelopment server credentials: demo / demo\n\n'
exec sanea "${server_command[@]}" "$@"
