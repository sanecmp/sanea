"""Consistent labels for selections covering every item."""

import pytest
from django.utils.translation import override

from sanea.core.forms import ActivityFilterForm, CommandFilterForm, ComputerFilterForm, DashboardFilterForm, IssueFilterForm
from sanea.core.forms.base import SaneaForm


@pytest.mark.parametrize("language, expected", [("en", "All"), ("ru", "Все")])
@pytest.mark.parametrize(
    "form_type, aggregate_choices",
    [
        (DashboardFilterForm, {"person": ""}),
        (ActivityFilterForm, {"person": "", "computer": "", "account": ""}),
        (ComputerFilterForm, {"access": "", "connection": "", "config_delivery": ""}),
        (CommandFilterForm, {"command_computer": "", "command_type": "", "command_status": ""}),
        (IssueFilterForm, {"computer": "", "period": "all"}),
    ],
)
def test_filter_aggregate_choices_use_one_label(
    form_type: type[SaneaForm], aggregate_choices: dict[str, str], language: str, expected: str,
) -> None:

    with override(language):
        form = form_type()

        for field_name, value in aggregate_choices.items():
            assert f"{dict(form.fields[field_name].choices)[value]}" == expected
