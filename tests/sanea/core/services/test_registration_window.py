"""Tests for the short-lived sanex registration window."""

import re
from concurrent.futures import ThreadPoolExecutor

from sanea.core.models import Computer, ComputerStatus
from sanea.core.services.registration_window import RegistrationWindow, is_registration_discovery_available, registration_window


def test_open_reuses_active_code_without_extending_window() -> None:
    now = [100.0]
    window = RegistrationWindow(clock=lambda: now[0])

    first = window.open()
    now[0] += 5
    second = window.open()

    assert re.fullmatch(r"[A-HJ-KM-NP-Z2-9]{4}-[A-HJ-KM-NP-Z2-9]{4}", first.code)
    assert first.remaining_display == "00:30"
    assert second.code == first.code
    assert second.remaining_milliseconds == 25_000


def test_wrong_code_does_not_close_or_extend_window() -> None:
    now = [100.0]
    window = RegistrationWindow(clock=lambda: now[0])
    opened = window.open()
    now[0] += 12

    assert window.claim("WRNG-CODE") is False
    assert window.get_snapshot().code == opened.code
    assert window.get_snapshot().remaining_milliseconds == 18_000


def test_first_matching_claim_atomically_closes_window() -> None:
    window = RegistrationWindow()
    code = window.open().code

    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(window.claim, [code.lower()] * 8))

    assert results.count(True) == 1
    assert results.count(False) == 7
    assert window.get_snapshot() is None


def test_window_expires_after_thirty_seconds() -> None:
    now = [100.0]
    window = RegistrationWindow(clock=lambda: now[0])
    window.open()

    now[0] = 130.0

    assert window.get_snapshot() is None
    assert window.claim("ABCD-EFGH") is False


def test_registration_discovery_is_available_for_open_window() -> None:
    registration_window.close()
    try:
        registration_window.open()

        assert is_registration_discovery_available() is True
    finally:
        registration_window.close()


def test_registration_discovery_is_available_for_pending_computer() -> None:
    registration_window.close()
    Computer.objects.create(
        hostname="pending-computer",
        status=ComputerStatus.PENDING,
    )

    assert is_registration_discovery_available() is True


def test_registration_discovery_is_closed_without_window_or_pending_computer() -> None:
    registration_window.close()

    assert is_registration_discovery_available() is False
