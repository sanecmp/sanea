"""Forms for managing limits templates."""

from django import forms
from django.utils.translation import gettext_lazy as _

from ..models import LimitsTemplate, Person
from .base import SaneaModelForm


class LimitsTemplateForm(SaneaModelForm):
    """Edit a template and the people using it by default."""

    people = forms.ModelMultipleChoiceField(
        label=_("Default template for"),
        queryset=Person.objects.all(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
    )

    class Meta:
        model = LimitsTemplate
        fields = ("name",)
        help_texts = {"name": ""}

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)

        if self.instance.pk:
            self.fields["people"].initial = self.instance.people.all()
