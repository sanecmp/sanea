"""Tests for host timezone discovery using isolated filesystem sources."""

from pathlib import Path

import pytest

from sanea.utils import timezone as host_timezone


@pytest.fixture
def timezone_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path, Path]:
    localtime = tmp_path / "localtime"
    timezone_file = tmp_path / "timezone"
    zoneinfo_dir = tmp_path / "zoneinfo"
    monkeypatch.delenv("TZ", raising=False)
    monkeypatch.setattr(host_timezone, "LOCALTIME_PATH", localtime)
    monkeypatch.setattr(host_timezone, "TIMEZONE_PATH", timezone_file)
    monkeypatch.setattr(host_timezone, "TZPATH", (f"{zoneinfo_dir}",))
    return localtime, timezone_file, zoneinfo_dir


@pytest.mark.parametrize(
    ("environment_zone", "symlink_zone", "file_zone", "expected"),
    [
        ("America/New_York", "Europe/Berlin", "Asia/Novosibirsk", "America/New_York"),
        (":America/New_York", "Europe/Berlin", "Asia/Novosibirsk", "America/New_York"),
        ("", "Europe/Berlin", "Asia/Novosibirsk", "Europe/Berlin"),
        ("Unknown/Timezone", "Europe/Berlin", "Asia/Novosibirsk", "Europe/Berlin"),
        ("", "Unknown/Timezone", "Asia/Novosibirsk", "Asia/Novosibirsk"),
        ("Unknown/Timezone", "Unknown/Timezone", "Unknown/Timezone", "UTC"),
        ("", "Unknown/Timezone", "", "UTC"),
    ],
)
def test_timezone_source_priority_and_validation(
    timezone_paths: tuple[Path, Path, Path],
    monkeypatch: pytest.MonkeyPatch,
    environment_zone: str,
    symlink_zone: str,
    file_zone: str,
    expected: str,
) -> None:
    localtime, timezone_file, zoneinfo_dir = timezone_paths
    zone_file = zoneinfo_dir / symlink_zone
    zone_file.parent.mkdir(parents=True)
    zone_file.write_text("synthetic timezone target\n", encoding="utf-8")
    localtime.symlink_to(zone_file)
    timezone_file.write_text(f"{file_zone}\n", encoding="utf-8")
    monkeypatch.setenv("TZ", environment_zone)

    assert host_timezone.get_local_timezone_name() == expected


def test_timezone_falls_back_to_utc_when_sources_are_missing(timezone_paths: tuple[Path, Path, Path]) -> None:
    assert host_timezone.get_local_timezone_name() == "UTC"


def test_timezone_file_is_used_when_localtime_has_no_zoneinfo_name(timezone_paths: tuple[Path, Path, Path]) -> None:
    localtime, timezone_file, _zoneinfo_dir = timezone_paths
    localtime.write_bytes(b"synthetic copied timezone file")
    timezone_file.write_text("  Asia/Novosibirsk\n", encoding="utf-8")

    assert host_timezone.get_local_timezone_name() == "Asia/Novosibirsk"


def test_timezone_falls_back_to_utc_when_timezone_file_cannot_be_decoded(
    timezone_paths: tuple[Path, Path, Path],
) -> None:
    _localtime, timezone_file, _zoneinfo_dir = timezone_paths
    timezone_file.write_bytes(b"\xff")

    assert host_timezone.get_local_timezone_name() == "UTC"
