"""Tests for stable accounting-identifier allocation."""

from typing import Any

import pytest

from sanea.core.models import AppRule, IdentifierSequence, Range, SessionRule


@pytest.mark.parametrize(
    ("model", "existing_ident"),
    (
        (Range, 30),
        (SessionRule, 10),
        (AppRule, 20),
    ),
)
def test_allocates_unique_identifiers_across_snapshot_branches(
    limits_snapshot_graph: dict[str, Any],
    model: type[Range | SessionRule | AppRule],
    existing_ident: int,
) -> None:
    first = IdentifierSequence.allocate(model)
    second = IdentifierSequence.allocate(model)

    assert first == existing_ident + 1
    assert second == first + 1


def test_does_not_reuse_identifier_after_highest_row_is_deleted(
    limits_snapshot_graph: dict[str, Any],
) -> None:
    first = IdentifierSequence.allocate(Range)
    limits_snapshot_graph["range"].delete()

    second = IdentifierSequence.allocate(Range)

    assert second == first + 1
