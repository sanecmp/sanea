"""Explicit account choices are scoped to a template's recipients."""

import pytest

from sanea.core.forms import TemplatePropagationForm
from sanea.core.models import Account, Computer, Limits, LimitsTemplate, Person


@pytest.mark.parametrize("selection", ["own", "foreign", "empty", "unassigned"])
def test_template_application_rejects_accounts_outside_its_people(
    activity_filter_records: dict[str, Account | Computer | Person], selection: str,
) -> None:
    person = activity_filter_records["person"]
    account = activity_filter_records["account"]
    foreign = activity_filter_records["other_account"]
    template = LimitsTemplate.objects.create(name="Synthetic template", current_limits=Limits.objects.create())

    if selection != "unassigned":
        person.limits_tpl = template
        person.save()

    selections = {"own": [account.pk], "foreign": [foreign.pk], "empty": [], "unassigned": [account.pk]}
    form = TemplatePropagationForm({"accounts": selections[selection]}, template=template)

    if selection == "own":
        assert form.is_valid(), form.errors.as_json()
        assert list(form.cleaned_data["accounts"]) == [account]

    else:
        assert not form.is_valid()
        assert set(form.errors) == {"accounts"}


def test_template_application_preselects_readable_recipient_accounts(
    activity_filter_records: dict[str, Account | Computer | Person],
) -> None:
    person = activity_filter_records["person"]
    account = activity_filter_records["account"]
    template = LimitsTemplate.objects.create(name="Synthetic template", current_limits=Limits.objects.create())
    person.limits_tpl = template
    person.save()
    form = TemplatePropagationForm(template=template)

    content = f"{form}"

    assert list(form.fields["accounts"].initial) == [account]
    assert f"{account.name or account.login} · study-pc" in content
    assert "spare-pc" not in content
    assert "checked" in content
    assert "type=\"checkbox\"" in content
    assert "class=\"sanea-checklist\"" in content
    assert "class=\"form-check-input\"" not in content
