"""Migration consistency tests."""
from collections.abc import Callable


def test_core_migrations_are_current(check_migrations: Callable[..., bool]) -> None:
    assert check_migrations(app="core") is True
