"""Form for an exact ignored process name."""

from ..models import PrcExclusion
from .base import SaneaModelForm


class PrcExclusionForm(SaneaModelForm):
    """Validate one process name before adding it to the global list."""

    class Meta:
        model = PrcExclusion
        fields = ("prc_name",)
