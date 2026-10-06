"""Forms for managing people."""


from ..models import Person
from .base import SaneaModelForm


class PersonForm(SaneaModelForm):
    """Edit fields owned directly by a person."""

    class Meta:
        model = Person
        fields = ("name", "limits_tpl")
