"""Forms for managing application rules."""


from ..models import AppRule
from .base import SaneaModelForm


class AppRuleForm(SaneaModelForm):
    """Edit application quotas and recognition conditions."""

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
