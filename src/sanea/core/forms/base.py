"""Shared form classes and rendering configuration."""

from types import MethodType

from django.forms import CheckboxSelectMultiple
from siteforms.composers.base import ALL_FIELDS, ALL_GROUPS, ALL_ROWS
from siteforms.composers.bootstrap5 import Bootstrap5
from siteforms.fields import EnhancedField
from siteforms.toolbox import Form, ModelForm


class SaneaFormMixin:
    """Apply the common siteforms Bootstrap rendering policy."""

    class Composer(Bootstrap5):
        opt_render_form_tag = False
        opt_feedback_valid = False
        attrs = {**Bootstrap5.attrs, CheckboxSelectMultiple: {"class": "sanea-checklist"}}

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)

        for field in self.fields.values():
            field.get_bound_field = MethodType(EnhancedField.get_bound_field, field)

        self._bound_fields_cache.clear()


class SaneaForm(SaneaFormMixin, Form):
    """Base class for non-model sanea forms."""


class SaneaModelForm(SaneaFormMixin, ModelForm):
    """Base class for model-backed sanea forms."""


class GridModelForm(SaneaModelForm):
    """Arrange model fields in responsive Bootstrap rows."""

    class Composer(SaneaModelForm.Composer):
        attrs = {ALL_ROWS: {"class": "row gx-3"}}
        wrappers = {
            ALL_FIELDS: "<div class=\"col-12 col-sm mb-3\">{field}</div>",
            ALL_GROUPS: "<div>{rows}</div>",
        }
