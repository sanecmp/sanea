"""Forms for managing limits templates."""


from ..models import LimitsTemplate
from .base import SaneaModelForm


class LimitsTemplateForm(SaneaModelForm):
    """Create or rename a limits template."""

    class Meta:
        model = LimitsTemplate
        fields = ("name",)
