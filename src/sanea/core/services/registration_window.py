"""Short-lived authorization window for registering one sanex client."""

import logging
import math
import secrets
import time
from collections.abc import Callable
from dataclasses import dataclass
from threading import Lock

from django.db import DatabaseError, close_old_connections

from ..models import Computer


_CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
_CODE_LENGTH = 8


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RegistrationWindowSnapshot:
    """Public state needed to show an active registration window."""

    code: str
    remaining_milliseconds: int
    duration_milliseconds: int

    @property
    def remaining_display(self) -> str:
        """Return a stable MM:SS value for the initial page render."""
        seconds = math.ceil(self.remaining_milliseconds / 1000)
        minutes, seconds = divmod(seconds, 60)
        return f"{minutes:02d}:{seconds:02d}"


class RegistrationWindow:
    """Keep one process-local registration code and claim it atomically."""

    def __init__(
        self,
        duration_seconds: int = 30,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._duration_seconds = duration_seconds
        self._clock = clock
        self._lock = Lock()
        self._code: str | None = None
        self._expires_at = 0.0

    def open(self) -> RegistrationWindowSnapshot:
        """Open a window or return the currently active one without extending it."""
        get_snapshot = self._get_snapshot_unlocked

        with self._lock:
            snapshot = get_snapshot()

            if snapshot is not None:
                return snapshot

            raw_code = "".join(
                secrets.choice(_CODE_ALPHABET) for _ in range(_CODE_LENGTH)
            )
            self._code = f"{raw_code[:4]}-{raw_code[4:]}"
            self._expires_at = self._clock() + self._duration_seconds
            return get_snapshot()

    def get_snapshot(self) -> RegistrationWindowSnapshot | None:
        """Return the active window without exposing expired state."""

        with self._lock:
            return self._get_snapshot_unlocked()

    def claim(self, code: str) -> bool:
        """Close and claim the window if the supplied code matches."""
        normalized_code = code.strip().upper()

        with self._lock:
            snapshot = self._get_snapshot_unlocked()

            if snapshot is None or not secrets.compare_digest(
                snapshot.code,
                normalized_code,
            ):
                return False

            self._clear_unlocked()
            return True

    def close(self) -> None:
        """Close the current window without claiming it."""

        with self._lock:
            self._clear_unlocked()

    def _get_snapshot_unlocked(self) -> RegistrationWindowSnapshot | None:
        code = self._code

        if code is None:
            return None

        remaining = self._expires_at - self._clock()

        if remaining <= 0:
            self._clear_unlocked()
            return None

        return RegistrationWindowSnapshot(
            code=code,
            remaining_milliseconds=max(1, math.ceil(remaining * 1000)),
            duration_milliseconds=self._duration_seconds * 1000,
        )

    def _clear_unlocked(self) -> None:
        self._code = None
        self._expires_at = 0.0


def is_registration_discovery_available() -> bool:
    """Return whether a sanex registration can start or resume."""

    if registration_window.get_snapshot() is not None:
        return True

    close_old_connections()
    try:
        return Computer.has_pending_registration()

    except DatabaseError:
        logger.exception("Unable to inspect pending sanex registrations")
        return False
    finally:
        close_old_connections()


registration_window = RegistrationWindow()
