"""Forms for managing session rules."""

from siteforms.composers.base import FORM

from ..models import SessionRule
from .base import GridModelForm


class SessionRuleForm(GridModelForm):
    """Edit session quota fields within one limits set."""

    class Composer(GridModelForm.Composer):
        layout = {FORM: {"rule": ["apply", "name", ("max_sessions", "max_duration", "break_duration")]}}

    class Meta:
        model = SessionRule
        fields = (
            "name",
            "apply",
            "max_sessions",
            "max_duration",
            "break_duration",
        )
