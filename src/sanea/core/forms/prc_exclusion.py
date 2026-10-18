"""Form for an exact ignored process name."""

import json

from django.utils.translation import gettext_lazy as _

from ..models import PrcExclusion
from .base import SaneaModelForm


class PrcExclusionForm(SaneaModelForm):
    """Validate an added or edited name, reusing a previously removed row."""

    def __init__(self, *args: object, suggestions: tuple[str, ...] = (), **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        self.fields["prc_name"].widget.attrs.update({
            "data-select-suggestions": json.dumps(suggestions, ensure_ascii=False),
            "data-select-create-label": _("Use:"),
            "placeholder": _("Choose or enter a name"),
        })

        if self.is_bound and not self.instance.pk:
            name = self.data.get(self.add_prefix("prc_name"), "").strip()
            removed = PrcExclusion.objects.filter(prc_name=name, apply=False).first()

            if removed is not None:
                self.instance = removed

    class Meta:
        model = PrcExclusion
        fields = ("prc_name",)
        help_texts = {"prc_name": _("From recorded activity or enter manually. Case-sensitive, up to 15 characters.")}
