"""Default empty choices use the interface language in all editors."""

import pytest
from django.utils.translation import override

from sanea.core.forms import AccountForm, AppRuleForm
from sanea.core.forms.base import SaneaModelForm


@pytest.mark.parametrize(
    "form_type, field_names",
    [
        (AccountForm, ("person",)),
        (AppRuleForm, ("prc_name_match", "exe_match", "wnd_title_match")),
    ],
    ids=["related-object", "model-choices"],
)
@pytest.mark.parametrize(
    "language, expected", [("en", "- Select an option -"), ("ru", "—")],
)
def test_editor_empty_choices_use_the_interface_language(
    form_type: type[SaneaModelForm], field_names: tuple[str, ...], language: str, expected: str,
) -> None:

    with override(language):
        form = form_type()

        for field_name in field_names:
            value, label = next(iter(form.fields[field_name].choices))

            assert value == ""
            assert f"{label}" == expected
            assert f">{expected}</option>" in f"{form[field_name]}"
