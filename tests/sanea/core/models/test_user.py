"""Tests for browser users."""

from typing import Any
from collections.abc import Callable

from sanea.core.models import User


def test_can_reference_person(domain_graph: dict[str, Any], user_create: Callable[..., User]) -> None:
    person = domain_graph["person"]
    user = user_create(attributes={"person": person})

    assert user.person == person
