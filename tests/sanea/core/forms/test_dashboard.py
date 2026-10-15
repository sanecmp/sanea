"""Tests for shared dashboard filters."""

import pytest

from sanea.core.forms import DashboardFilterForm
from sanea.core.models import Account, Computer, Person


@pytest.mark.parametrize(
    ("period", "hours"), [("24-hours", 24), ("48-hours", 48), ("7-days", 168), ("30-days", 720)],
)
def test_dashboard_filter_supports_the_requested_rolling_periods(period: str, hours: int) -> None:
    form = DashboardFilterForm({"period": period})

    assert form.is_valid(), form.errors.as_json()
    assert form.get_hour_count() == hours
    assert DashboardFilterForm().fields["period"].initial == "48-hours"
    assert list(dict(form.fields["period"].choices)) == ["24-hours", "48-hours", "7-days", "30-days"]


def test_dashboard_filter_lists_all_people_by_name_and_scopes_all_their_collecting_accounts(
    activity_filter_records: dict[str, Account | Computer | Person],
) -> None:
    person = activity_filter_records["person"]
    second_account = Account.objects.create(
        computer=activity_filter_records["other_computer"], person=person, uid=1003, collect=True,
    )
    Account.objects.create(computer=activity_filter_records["other_computer"], person=person, uid=1004, collect=False)
    inactive = Person.objects.create(name="Synthetic inactive person")
    form = DashboardFilterForm({"period": "48-hours", "person": person.pk})

    assert form.is_valid(), form.errors.as_json()
    assert set(form.get_accounts()) == {activity_filter_records["account"], second_account}
    assert list(form.fields["person"].queryset) == sorted(
        [person, activity_filter_records["other_person"], inactive], key=lambda item: (item.name, item.pk),
    )


@pytest.mark.parametrize("data", [{"period": "invalid"}, {"period": "48-hours", "person": "999999"}])
def test_dashboard_filter_rejects_invalid_choices(data: dict[str, str]) -> None:
    form = DashboardFilterForm(data)

    assert not form.is_valid()

    with pytest.raises(ValueError, match="dashboard filters must be valid"):
        form.get_accounts()

    with pytest.raises(ValueError, match="dashboard filters must be valid"):
        form.get_hour_count()
