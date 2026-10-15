"""Application recognition labels stay compact in both editors."""

import pytest
from django.utils.translation import override

from sanea.core.forms import AppRuleForm
from sanea.core.forms.account_limits import AccountAppForm


@pytest.mark.parametrize(
    "form_type, form_options",
    [(AppRuleForm, {}), (AccountAppForm, {"rules": (), "rule_rows": {}})],
    ids=["template", "account"],
)
@pytest.mark.parametrize(
    "language, short_label, accessible_labels",
    [
        ("en", "Comparison", ("Process name match", "Executable match", "Window title match")),
        ("ru", "Сравнение", (
            "Сопоставление имени процесса", "Сопоставление исполняемого файла", "Сопоставление заголовка окна",
        )),
    ],
)
def test_app_matching_fields_use_short_labels_without_losing_accessible_names(
    form_type: type[AppRuleForm], form_options: dict[str, object], language: str,
    short_label: str, accessible_labels: tuple[str, ...],
) -> None:

    with override(language):
        form = form_type(**form_options)

        for field_name, accessible_label in zip(("prc_name_match", "exe_match", "wnd_title_match"), accessible_labels):
            field = form[field_name]

            assert f"{field.label}" == short_label
            assert f'aria-label="{accessible_label}"' in f"{field}"
