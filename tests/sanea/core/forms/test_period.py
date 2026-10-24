"""Shared period calendars and local-day validation across reports."""

import json
from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest
from django.utils import timezone

from sanea.core.forms import ActivityFilterForm, DashboardFilterForm, IssueFilterForm
from sanea.core.forms.period import PeriodFilterForm


@pytest.mark.parametrize("form_type", [ActivityFilterForm, DashboardFilterForm, IssueFilterForm])
def test_all_reporting_filters_share_one_visible_period_calendar(form_type: type[PeriodFilterForm]) -> None:
    form = form_type(prefix="report")
    presets = json.loads(form.fields["day"].widget.attrs["data-period-presets"])

    assert "period" not in [field.name for field in form.visible_fields()]
    assert form.fields["period"].widget.is_hidden
    assert [preset["value"] for preset in presets] == [value for value, label in form_type.PERIOD_PRESETS]
    assert form.fields["day"].label == "Period"
    assert form.fields["day"].widget.attrs["data-period-field"] == "report-period"


@pytest.mark.parametrize("form_type", [ActivityFilterForm, DashboardFilterForm, IssueFilterForm])
@pytest.mark.parametrize("day", ["", "2026-02-29", "24.10.2026", "9999-12-31"])
def test_reporting_calendar_rejects_invalid_iso_days(form_type: type[PeriodFilterForm], day: str) -> None:
    form = form_type({"period": "day", "day": day})

    assert not form.is_valid()
    assert "day" in form.errors


@pytest.mark.parametrize("form_type", [ActivityFilterForm, DashboardFilterForm, IssueFilterForm])
def test_native_date_submission_overrides_the_initial_preset(form_type: type[PeriodFilterForm]) -> None:
    form = form_type({"period": form_type.PERIOD_INITIAL, "day": "2026-10-23"})

    assert form.is_valid(), form.errors.as_json()
    assert form.cleaned_data["period"] == "day"
    assert form.get_selected_day_range() == (date(2026, 10, 23), date(2026, 10, 24))


@pytest.mark.parametrize(("day", "hours"), [("2026-03-08", 23), ("2026-11-01", 25)])
def test_calendar_timestamp_bounds_follow_local_daylight_saving_time(day: str, hours: int) -> None:
    form = DashboardFilterForm({"period": "day", "day": day})
    zone = ZoneInfo("America/New_York")

    with timezone.override(zone):
        since, till = form.get_timestamp_range(datetime(2026, 10, 24, tzinfo=zone))

    assert till - since == hours * 3_600
    assert datetime.fromtimestamp(since, zone).date().isoformat() == day
    assert datetime.fromtimestamp(till, zone).hour == 0
