"""Forms for managing people."""

from django.utils.translation import pgettext_lazy

from ..models import Person
from .base import SaneaModelForm


class PersonForm(SaneaModelForm):
    """Edit fields owned directly by a person."""

    class Meta:
        model = Person
        fields = ("name",)
        labels = {"name": pgettext_lazy("person", "Name")}
        help_texts = {"name": ""}
