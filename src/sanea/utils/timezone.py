"""Resolve the host's named timezone without changing its clock settings."""

import os
from pathlib import Path
from zoneinfo import TZPATH, ZoneInfo, ZoneInfoNotFoundError


LOCALTIME_PATH = Path("/etc/localtime")
TIMEZONE_PATH = Path("/etc/timezone")


def get_local_timezone_name() -> str:
    """Read TZ or the system timezone, falling back to UTC when unavailable."""
    candidates = [os.environ.get("TZ", "").removeprefix(":")]

    try:
        localtime = LOCALTIME_PATH.resolve(strict=True)

    except OSError:
        localtime = None

    if localtime is not None:

        for directory in TZPATH:

            try:
                candidates.append(localtime.relative_to(directory).as_posix())

            except ValueError:
                continue

    try:
        candidates.append(TIMEZONE_PATH.read_text(encoding="utf-8").strip())

    except (OSError, UnicodeError):
        pass

    for name in candidates:

        try:
            ZoneInfo(name)

        except (ValueError, ZoneInfoNotFoundError):
            continue

        return name

    return "UTC"
