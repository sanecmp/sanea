"""Tests for the parent dashboard."""

import json
from collections.abc import Callable
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from django.test import Client
from django.urls import reverse
from django.utils import timezone
from django.utils.formats import date_format
from time_machine import TimeMachineFixture

from sanea import __version__
from sanea.core.models import Account, Computer, Person, User


def read_chart(content: str, identifier: str) -> dict[str, object]:
    """Read the serialized chart delivered to the browser."""
    serialized = content.split(f'<script id="{identifier}" type="application/json">')[1].split("</script>")[0]
    return json.loads(serialized)


@pytest.mark.parametrize(
    "request_options",
    [
        {},
        {"HTTP_HX_REQUEST": "true", "HTTP_HX_TRIGGER": "dashboard-usage"},
        {"HTTP_HX_REQUEST": "true", "HTTP_HX_TRIGGER": "dashboard-filter"},
    ],
    ids=["page", "refresh", "filter"],
)
def test_dashboard_requires_authenticated_management_user(
    request_client: Callable[..., Client],
    user_create: Callable[..., User],
    request_options: dict[str, str],
) -> None:
    anonymous_response = request_client().get(reverse("core:dashboard"), **request_options)
    regular_user = user_create()
    regular_response = request_client(user=regular_user).get(reverse("core:dashboard"), **request_options)

    assert anonymous_response.status_code == 302
    assert anonymous_response.url.startswith(reverse("core:sign_in"))
    assert reverse("admin:index") not in anonymous_response.url
    assert regular_response.status_code == 403


def test_dashboard_uses_local_layout_without_duplicate_navigation(
    request_client: Callable[..., Client], user_create: Callable[..., User],
) -> None:
    staff_user = user_create(attributes={"is_staff": True})

    response = request_client(user=staff_user).get(reverse("core:dashboard"))
    content = response.content.decode()
    main = content.split("<main", 1)[1].split("</main>", 1)[0]

    assert response.status_code == 200
    assert "<span>sane</span><span class=\"sanea-wordmark-accent\">a</span>" in content
    assert content.count('class="sanea-brand-logo"') == 3
    assert "vendor/bootstrap/bootstrap.min.css" in content
    assert "sanea/css/dashboard.css" in content
    assert 'href="/static/sanea/favicon.svg"' in content
    assert "vendor/htmx/htmx.min.js" in content
    assert "vendor/tom-select/tom-select.bootstrap5.min.css" in content
    assert "vendor/tom-select/tom-select.complete.min.js" in content
    assert "sanea/js/searchable-selects.js" in content
    assert 'data-select-search="Search"' in content
    assert 'data-select-empty="No matches"' in content
    assert "https://" not in content
    assert content.index("<span>Statistics</span>") < content.index("<span>People</span>")
    assert "vendor/chartjs/chart.umd.min.js" in content
    assert "sanea/js/activity-charts.js" in content
    assert f"sanea {__version__}" in content
    assert "id=\"activity-filter\"" not in content
    assert "sanea-summary-card" not in main
    assert "system-status" not in main
    assert "Manage computers" not in main
    assert "View issues" not in main
    assert "<a " not in main
    assert '<option value="48-hours" selected>' in main
    assert "Time spent" in main
    assert "Application usage" in main
    assert "No activity collection for this selection." in main
    assert 'id="dashboard-filter"' in main
    assert 'hx-target="#dashboard-area"' in main
    assert 'hx-push-url="true"' in main
    assert 'hx-include="#dashboard-filter"' in main


@pytest.mark.parametrize(
    "request_options",
    [{}, {"HTTP_HX_REQUEST": "true", "HTTP_HX_TRIGGER": "dashboard-usage"}],
    ids=["page", "fragment"],
)
def test_dashboard_renders_the_rolling_window_by_person_and_application(
    request_client: Callable[..., Client],
    user_create: Callable[..., User],
    computer_record: Computer,
    person_record: Person,
    activity_run_create: Callable[..., None],
    request_options: dict[str, str],
) -> None:
    account = computer_record.accounts.get()
    account.person = person_record
    account.save(update_fields=("person",))
    idle_person = Person.objects.create(name="Synthetic inactive person")
    till = int(timezone.now().timestamp())
    since = till - 48 * 3_600
    activity_run_create(account, started=since, finished=since + 3_600, duration=1_800)
    activity_run_create(account, kind="prc", started=till - 7_200, finished=till - 3_600, duration=600)
    guest = Account.objects.create(computer=computer_record, uid=1002, collect=True)
    activity_run_create(guest, started=till - 3_600, finished=till, duration=600)
    client = request_client(user=user_create(attributes={"is_staff": True}))
    zone = ZoneInfo("America/New_York")

    with timezone.override(zone):
        response = client.get(reverse("core:dashboard"), **request_options)

    content = response.content.decode()
    people = read_chart(content, "dashboard-people-data")
    applications = read_chart(content, "dashboard-applications-data")
    series = {dataset["label"]: dataset["data"] for dataset in people["datasets"]}

    assert response.status_code == 200
    assert 'id="dashboard-usage"' in content
    assert 'aria-label="Time spent"' in content
    assert 'hx-trigger="every 60s [!document.hidden]"' in content
    assert len(people["labels"]) == 48
    first_hour = datetime.fromtimestamp(since, zone)
    last_hour = datetime.fromtimestamp(till - 3_600, zone)
    assert people["labels"][0] == [date_format(first_hour, "d.m"), date_format(first_hour, "H:i")]
    assert people["labels"][-1] == [date_format(last_hour, "d.m"), date_format(last_hour, "H:i")]
    assert series[person_record.name] == [1_800] + [0] * 47
    assert series[idle_person.name] == [0] * 48
    assert series["No user"] == [0] * 47 + [600]
    assert applications["labels"] == ["synthetic-app"]
    assert applications["datasets"][0]["data"] == [600]
    assert applications["indexAxis"] == "y"
    assert "America/New_York" in content
    assert "Asia/Novosibirsk" not in content
    assert "estimated proportionally" not in content
    assert "Simultaneous use" not in content
    assert "Manage computers" not in content


def test_dashboard_has_clear_empty_states_and_russian_text(
    request_client: Callable[..., Client],
    user_create: Callable[..., User],
    computer_record: Computer,
) -> None:
    client = request_client(user=user_create(attributes={"is_staff": True}))

    english = client.get(reverse("core:dashboard")).content.decode()
    russian = client.get(reverse("core:dashboard"), HTTP_ACCEPT_LANGUAGE="ru").content.decode()

    assert "No activity collection" not in english
    assert "No completed sessions for this period." in english
    assert "No completed application runs for this period." in english
    assert "48 часов" in russian
    assert 'id="people-usage-heading">Затраченное время</h2>' in russian
    assert 'data-activity-chart="dashboard-people-data"' not in english
    assert 'data-activity-chart="dashboard-applications-data"' not in english


def test_dashboard_refresh_advances_the_window_without_returning_navigation(
    request_client: Callable[..., Client],
    user_create: Callable[..., User],
    calendar_time: TimeMachineFixture,
) -> None:
    client = request_client(user=user_create(attributes={"is_staff": True}))
    calendar_time.move_to("2026-10-06T12:01:00+00:00", tick=False)

    response = client.get(reverse("core:dashboard"), HTTP_HX_REQUEST="true", HTTP_HX_TRIGGER="dashboard-usage")
    content = response.content.decode()

    assert response.status_code == 200
    assert 'id="dashboard-usage"' in content
    assert date_format(timezone.localtime(), "SHORT_DATETIME_FORMAT") in content
    assert "sanea-shell" not in content


@pytest.mark.parametrize(
    ("period", "hours", "buckets"),
    [("24-hours", 24, 24), ("48-hours", 48, 48), ("7-days", 168, 7), ("30-days", 720, 30), (None, 48, 48)],
)
@pytest.mark.parametrize(
    ("request_options", "contains_filter"),
    [
        ({}, True),
        ({"HTTP_HX_REQUEST": "true", "HTTP_HX_TRIGGER": "dashboard-filter"}, True),
        ({"HTTP_HX_REQUEST": "true", "HTTP_HX_TRIGGER": "dashboard-usage"}, False),
    ],
    ids=["page", "filter", "refresh"],
)
def test_dashboard_applies_the_same_period_and_person_to_both_charts(
    request_client: Callable[..., Client],
    user_create: Callable[..., User],
    computer_record: Computer,
    person_record: Person,
    activity_run_create: Callable[..., None],
    period: str | None,
    hours: int,
    buckets: int,
    request_options: dict[str, str],
    contains_filter: bool,
) -> None:
    account = computer_record.accounts.get()
    account.person = person_record
    account.save(update_fields=("person",))
    other_person = Person.objects.create(name="Synthetic other person")
    other = Account.objects.create(computer=computer_record, person=other_person, uid=1002, collect=True)
    till = int(timezone.now().timestamp())
    since = till - hours * 3_600

    for kind in ("session", "prc"):
        activity_run_create(account, kind=kind, started=since, finished=since + 3_600, duration=600)
        activity_run_create(account, kind=kind, started=till - 3_600, finished=till, duration=900)

    activity_run_create(
        account, kind="prc", started=since - 3_600, finished=since,
        duration=3_600, prc_name="synthetic-old-app",
    )
    activity_run_create(other, started=till - 3_600, finished=till, duration=3_600)
    activity_run_create(
        other, kind="prc", started=till - 3_600, finished=till,
        duration=3_600, prc_name="synthetic-other-app",
    )
    filters = {"person": person_record.pk}

    if period is not None:
        filters["period"] = period

    client = request_client(user=user_create(attributes={"is_staff": True}))

    response = client.get(reverse("core:dashboard"), filters, **request_options)
    content = response.content.decode()
    people = read_chart(content, "dashboard-people-data")
    applications = read_chart(content, "dashboard-applications-data")

    assert response.status_code == 200
    assert ('id="dashboard-filter"' in content) is contains_filter
    assert len(people["labels"]) == buckets
    assert [dataset["label"] for dataset in people["datasets"]] == [person_record.name]
    assert sum(people["datasets"][0]["data"]) == 1_500
    assert applications["labels"] == ["synthetic-app"]
    assert applications["datasets"][0]["data"] == [1_500]
    assert "synthetic-old-app" not in content
    assert "synthetic-other-app" not in content
    assert date_format(datetime.fromtimestamp(since, timezone.get_current_timezone()), "SHORT_DATETIME_FORMAT") in content


@pytest.mark.parametrize("filters", [{"period": "wrong"}, {"period": "48-hours", "person": "999999"}])
def test_dashboard_rejects_invalid_filters_without_showing_unfiltered_charts(
    request_client: Callable[..., Client], user_create: Callable[..., User], filters: dict[str, str],
) -> None:
    client = request_client(user=user_create(attributes={"is_staff": True}))

    response = client.get(reverse("core:dashboard"), filters)
    content = response.content.decode()

    assert response.status_code == 200
    assert "Check the selected filters." in content
    assert 'data-activity-chart="dashboard-people-data"' not in content
    assert 'data-activity-chart="dashboard-applications-data"' not in content
