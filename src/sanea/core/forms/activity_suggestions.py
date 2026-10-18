"""Bounded recognition choices from explicitly scoped activity."""

from dataclasses import dataclass

from django.db.models import Max, QuerySet
from django.db.models.functions import Length

from ..models import ActivityEvent


@dataclass(frozen=True, slots=True)
class RecognitionSuggestion:
    """A recognition value with an optional application name for display."""

    value: str
    name: str = ""


def get_activity_suggestions(
    events: QuerySet[ActivityEvent], field_name: str, *, max_length: int, name_field: str | None = None,
) -> tuple[RecognitionSuggestion, ...]:
    """Read at most 50 recent values in one query, retaining the newest label."""
    fields = (field_name, name_field) if name_field else (field_name,)
    values = (
        events.annotate(value_length=Length(field_name))
        .filter(value_length__gt=0, value_length__lte=max_length)
        .values(*fields)
        .annotate(last_used=Max("timestamp"))
        .order_by("-last_used", *fields)
        .values_list(*fields)[:50]
    )
    unique: dict[str, RecognitionSuggestion] = {}

    for value, *names in values:

        if value.strip():
            # The newest name wins; renaming must not duplicate an ID in the list.
            unique.setdefault(value, RecognitionSuggestion(value, (names[0] or "") if names else ""))

    return tuple(unique.values())
