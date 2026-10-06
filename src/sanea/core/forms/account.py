"""Forms for managing local account settings."""


from ..models import Account
from .base import SaneaModelForm


class AccountForm(SaneaModelForm):
    """Edit settings owned by sanea for a sanex-reported account."""

    class Meta:
        model = Account
        fields = ("person", "collect", "apply")

    def clean(self) -> dict:
        """Collect events whenever limit enforcement is requested."""
        cleaned_data = super().clean()

        if cleaned_data.get("apply"):
            cleaned_data["collect"] = True
            self.instance.collect = True

        return cleaned_data
