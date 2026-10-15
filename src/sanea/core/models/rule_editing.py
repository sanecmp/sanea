"""Save form changes without modifying an assigned limits snapshot."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, TypeVar

from django.db import transaction
from django.forms import ModelForm

from .identifier_sequence import IdentifierSequence

if TYPE_CHECKING:
    from .base import TimestampedModel
    from .limits import Limits


RuleModelT = TypeVar("RuleModelT", bound="TimestampedModel")


@transaction.atomic
def save_limits_form(
    model: type[RuleModelT],
    form: ModelForm,
    limits: Limits,
    *,
    get_relations: Callable[[Limits], dict[str, object]],
    limits_lookup: str = "limits",
) -> RuleModelT:
    """Fork if needed, rebind parents, then validate and publish one rule."""
    target_limits = limits.checkout_for_edit()
    source = form.save(commit=False)

    if source.pk and target_limits.pk != limits.pk:
        rule = model.objects.get(**{limits_lookup: target_limits, "ident": source.ident})
        rule.apply_form(form)

    else:
        rule = source

    for field_name, value in get_relations(target_limits).items():
        setattr(rule, field_name, value)

    if not rule.pk:
        rule.ident = IdentifierSequence.allocate(model)

    rule.full_clean()
    rule.save()
    target_limits.materialize_computer_configs()
    return rule
