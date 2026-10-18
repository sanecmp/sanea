"""Ignored process choices supplement an editable exact process name."""

import json

import pytest
from django import forms
from django.utils.translation import override

from sanea.core.forms import PrcExclusionForm
from sanea.core.models import PrcExclusion


@pytest.mark.parametrize(
    "language, placeholder, help_text",
    [
        ("en", "Choose or enter a name", "From recorded activity or enter manually. Case-sensitive, up to 15 characters."),
        ("ru", "Выберите или введите имя", "Из статистики или вручную. С учётом регистра, до 15 символов."),
    ],
)
def test_ignored_process_choices_keep_a_translated_text_input(language: str, placeholder: str, help_text: str) -> None:

    with override(language):
        form = PrcExclusionForm(suggestions=("SteamWebHelper", "gjs-console"))
        field = form.fields["prc_name"]

        assert isinstance(field.widget, forms.TextInput)
        assert field.max_length == 15
        assert json.loads(field.widget.attrs["data-select-suggestions"]) == ["SteamWebHelper", "gjs-console"]
        assert f"{field.widget.attrs['placeholder']}" == placeholder
        assert help_text in form["prc_name"].as_field_group()


def test_ignored_process_choices_do_not_replace_a_saved_name_missing_from_activity() -> None:
    form = PrcExclusionForm(instance=PrcExclusion(prc_name="custom,process"), suggestions=("gjs-console",))

    assert form["prc_name"].value() == "custom,process"
    assert 'value="custom,process"' in f"{form['prc_name']}"
