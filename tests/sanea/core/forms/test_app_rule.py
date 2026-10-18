"""Application recognition labels stay compact in both editors."""

import pytest
from django import forms
from django.utils.translation import override

from sanea.core.forms import AppRuleForm
from sanea.core.forms.account_limits import AccountAppForm
from sanea.core.forms.activity_suggestions import RecognitionSuggestion


@pytest.mark.parametrize(
    "form_type, form_options",
    [(AppRuleForm, {}), (AccountAppForm, {"rules": (), "rule_rows": {}})],
    ids=["template", "account"],
)
@pytest.mark.parametrize(
    "language, expected_label, expected_help",
    [
        ("en", "Application", "From recorded activity. Optional."),
        ("ru", "Приложение", "Из статистики. Можно не выбирать."),
    ],
    ids=["english", "russian"],
)
def test_application_selector_shows_names_and_saves_identifiers(
    form_type: type[AppRuleForm], form_options: dict[str, object], language: str,
    expected_label: str, expected_help: str,
) -> None:

    with override(language):
        form = form_type(**form_options, suggestions={"app_id": (RecognitionSuggestion("steam:client", "Steam"),)})
        field = form.fields["app_id"]
        bound = form["app_id"]

        assert not field.required
        assert isinstance(field.widget, forms.Select)
        assert field.widget.attrs["data-select-search"] == "always"
        assert f"{field.label}" == expected_label
        assert f"{field.help_text}" == expected_help
        assert expected_help in bound.as_field_group()
        assert "<option value=\"steam:client\">Steam</option>" in f"{bound}"
        assert not form.suggestions


@pytest.mark.parametrize(
    "form_type, form_options",
    [(AppRuleForm, {}), (AccountAppForm, {"rules": (), "rule_rows": {}})],
    ids=["template", "account"],
)
def test_application_selector_preserves_a_saved_identifier_without_recent_activity(
    form_type: type[AppRuleForm], form_options: dict[str, object],
) -> None:
    form = form_type(**form_options, initial={"app_id": "steam:client"})
    bound = form["app_id"]

    assert "<option value=\"steam:client\" selected>steam:client</option>" in f"{bound}"
    assert f"{bound.help_text}" == "No applications in statistics yet. Use the conditions below."


def test_application_selector_distinguishes_matching_display_names() -> None:
    form = AppRuleForm(suggestions={"app_id": (
        RecognitionSuggestion("gjs:/apps/first/main.js", "main.js"),
        RecognitionSuggestion("gjs:/apps/second/main.js", "main.js"),
    )})

    assert list(form.fields["app_id"].widget.choices)[1:] == [
        ("gjs:/apps/first/main.js", "main.js (gjs:/apps/first/main.js)"),
        ("gjs:/apps/second/main.js", "main.js (gjs:/apps/second/main.js)"),
    ]


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
