"""Command-line entry point."""

import logging
import os
import sys
from collections.abc import Sequence

from django.conf import settings
from django.core.management import execute_from_command_line

from .utils.runtime import prepare_runtime_directories


def main(argv: Sequence[str] | None = None) -> None:
    """Expose Django management commands under the sanea entry point."""
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "sanea.settings")
    logging.basicConfig(
        level=logging.INFO,
        stream=sys.stderr,
        format="%(levelname)s %(name)s: %(message)s",
    )
    prepare_runtime_directories(settings.STATE_DIR, settings.DATABASE_PATH)
    execute_from_command_line(list(argv) if argv is not None else sys.argv)
