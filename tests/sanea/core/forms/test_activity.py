"""Tests for siteforms activity filters."""

from datetime import date

from sanea.core.forms import ActivityFilterForm
from sanea.core.forms.base import SaneaForm
from sanea.core.models import Account, Computer, Person


def test_activity_filter_uses_siteforms_and_returns_selected_scope(
    activity_filter_records: dict[str, Account | Computer | Person],
) -> None:
    account = activity_filter_records["account"]
    form = ActivityFilterForm(
        {
            "person": activity_filter_records["person"].pk,
            "computer": activity_filter_records["computer"].pk,
            "account": account.pk,
            "period": ActivityFilterForm.PERIOD_7_DAYS,
        }
    )

    assert isinstance(form, SaneaForm)
    assert form.is_valid(), form.errors.as_json()
    assert list(form.get_accounts()) == [account]
    assert form.get_date_range(date(2026, 10, 3)) == (
        date(2026, 9, 27),
        date(2026, 10, 4),
    )


def test_activity_filter_rejects_account_outside_selected_user(
    activity_filter_records: dict[str, Account | Computer | Person],
) -> None:
    form = ActivityFilterForm(
        {
            "person": activity_filter_records["other_person"].pk,
            "account": activity_filter_records["account"].pk,
            "period": ActivityFilterForm.PERIOD_TODAY,
        }
    )

    assert not form.is_valid()
    assert "account" in form.errors
