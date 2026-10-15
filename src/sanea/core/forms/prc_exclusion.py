"""Form for an exact ignored process name."""

from ..models import PrcExclusion
from .base import SaneaModelForm


class PrcExclusionForm(SaneaModelForm):
    """Validate an added or edited name, reusing a previously removed row."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)

        if self.is_bound and not self.instance.pk:
            name = self.data.get(self.add_prefix("prc_name"), "").strip()
            removed = PrcExclusion.objects.filter(prc_name=name, apply=False).first()

            if removed is not None:
                self.instance = removed

    class Meta:
        model = PrcExclusion
        fields = ("prc_name",)
