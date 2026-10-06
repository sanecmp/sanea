"""Forms for managing session rules."""


from ..models import SessionRule
from .base import SaneaModelForm


class SessionRuleForm(SaneaModelForm):
    """Edit session quota fields within one limits set."""

    class Meta:
        model = SessionRule
        fields = (
            "name",
            "apply",
            "max_sessions",
            "max_duration",
            "break_duration",
        )
