"""Forms for managing application rules."""


from django.db.models import Max, QuerySet
from django.db.models.functions import Length

from ..models import ActivityEvent, AppRule
from .base import SaneaModelForm


def get_app_suggestions(events: QuerySet[ActivityEvent]) -> dict[str, tuple[str, ...]]:
    """Offer recent recognition values from an explicitly scoped event set."""
    suggestions = {}

    for field_name in ("prc_name", "exe"):
        values = (
            events.annotate(value_length=Length(field_name))
            .filter(value_length__gt=0, value_length__lte=AppRule._meta.get_field(field_name).max_length)
            .values(field_name)
            .annotate(last_used=Max("timestamp"))
            .order_by("-last_used", field_name)
            .values_list(field_name, flat=True)[:50]
        )
        suggestions[field_name] = tuple(value for value in values if value.strip())

    return suggestions


class AppRuleForm(SaneaModelForm):
    """Edit application quotas and recognition conditions."""

    def __init__(
        self,
        *args: object,
        suggestions: dict[str, tuple[str, ...]] | None = None,
        **kwargs: object,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.suggestions: dict[str, tuple[str, ...]] = {}

        for field_name, values in (suggestions or {}).items():

            if values:
                datalist_id = f"{self[field_name].auto_id}-suggestions"
                self.fields[field_name].widget.attrs["list"] = datalist_id
                self.suggestions[datalist_id] = values

    class Meta:
        model = AppRule
        fields = (
            "name",
            "apply",
            "max_launches",
            "max_time",
            "prc_name",
            "prc_name_match",
            "exe",
            "exe_match",
            "wnd_title",
            "wnd_title_match",
        )
