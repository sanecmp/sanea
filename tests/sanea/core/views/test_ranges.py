"""Tests for weekly schedule range management."""

from typing import Any
from collections.abc import Callable
import re

import pytest
from django.urls import reverse
from django.test import Client

from sanea.core.models import Computer, Limits, LimitsTemplate, Range, SessionRule, User


def _ranges_url(limits: Limits) -> str:
    return reverse("core:ranges", kwargs={"limits_pk": limits.pk})


def test_ranges_requires_management_user(
    request_client: Callable[..., Client],
    user_create: Callable[..., User],
    limits_record: Limits,
) -> None:
    url = _ranges_url(limits_record)
    anonymous_response = request_client().get(url)
    regular_response = request_client(user=user_create()).get(url)

    assert anonymous_response.status_code == 302
    assert anonymous_response.url.startswith(reverse("core:sign_in"))
    assert regular_response.status_code == 403


@pytest.mark.parametrize(
    "included, status, icon",
    [(True, "Included in schedule", "check"), (False, "Not included in schedule", "ban")],
)
def test_ranges_list_schedule_intervals(
    request_client: Callable[..., Client],
    user_create: Callable[..., User],
    limits_record: Limits,
    range_record: Range,
    included: bool,
    status: str,
    icon: str,
) -> None:
    staff_user = user_create(attributes={"is_staff": True})
    range_record.apply = included
    range_record.save(update_fields=("apply", "updated"))

    response = request_client(user=staff_user).get(_ranges_url(limits_record))
    content = response.content.decode()

    assert response.status_code == 200
    assert "Friday" in content
    assert "15:00–20:00" in content
    assert range_record.session_rule.name in content
    assert "id=\"range-add\"" in content
    assert f"id=\"range-edit-{range_record.pk}\"" in content
    assert "←" not in content
    assert "<nav aria-label=\"Breadcrumbs\">" in content
    assert "<use href=\"#icon-plus\">" in content
    assert "<use href=\"#icon-edit\">" in content
    assert "<th scope=\"col\" class=\"text-center\">In schedule</th>" in content
    assert f"role=\"img\" title=\"{status}\" aria-label=\"{status}\"" in content
    assert f"<use href=\"#icon-{icon}\">" in content
    assert "badge" not in content
    assert "id=\"range-dialog\"" in content
    assert "data-editor-dialog" in content
    assert "id=\"range-save\"" not in content


@pytest.mark.parametrize("partial", [False, True], ids=["ordinary", "ajax"])
@pytest.mark.parametrize("creating", [False, True], ids=["edit", "add"])
def test_ranges_add_and_edit_in_one_dialog_with_day_and_times_on_the_same_row(
    request_client: Callable[..., Client], user_create: Callable[..., User],
    limits_record: Limits, range_record: Range, partial: bool, creating: bool,
) -> None:
    client = request_client(user=user_create(attributes={"is_staff": True}))
    reference = "new" if creating else f"{range_record.pk}"
    trigger = "range-add" if creating else f"range-edit-{range_record.pk}"
    headers = {"HTTP_HX_REQUEST": "true", "HTTP_HX_TRIGGER": trigger} if partial else {}

    response = client.get(_ranges_url(limits_record), {"range": reference}, **headers)
    content = response.content.decode()
    rows = re.split(r'<div\s+class="row gx-3">', content)
    interval_row = next(row for row in rows if "id=\"id_range-weekday\"" in row)

    assert response.status_code == 200
    assert "id=\"range-dialog-title\"" in content
    assert "id=\"range-save\" data-dialog-panel" in content
    assert "data-dialog-close" in content
    assert "id=\"id_range-since\"" in interval_row
    assert "id=\"id_range-till\"" in interval_row
    assert "id=\"id_range-apply\"" not in interval_row
    assert "id=\"id_range-session_rule\"" not in interval_row

    if not creating:
        assert "value=\"15:00\"" in interval_row
        assert "value=\"20:00\"" in interval_row


@pytest.mark.parametrize("partial", [False, True], ids=["ordinary", "ajax"])
def test_ranges_create_and_update(
    request_client: Callable[..., Client],
    user_create: Callable[..., User],
    limits_record: Limits,
    session_rule_record: SessionRule,
    range_record: Range,
    ranges_payload: dict[str, Any],
    partial: bool,
) -> None:
    staff_user = user_create(attributes={"is_staff": True})
    client = request_client(user=staff_user)
    url = _ranges_url(limits_record)
    ajax_headers = {
        "HTTP_HX_REQUEST": "true",
        "HTTP_HX_TRIGGER": "range-save",
    } if partial else {}
    created = ranges_payload["created"]

    create_response = client.post(
        url,
        {
            "__submit": "range",
            "range": "new",
            "range-apply": "on",
            "range-weekday": f"{created["weekday"]}",
            "range-since": created["since"],
            "range-till": created["till"],
            "range-session_rule": f"{session_rule_record.pk}",
        },
        **ajax_headers,
    )
    created_range = Range.objects.get(
        limits=limits_record,
        weekday=created["weekday"],
    )

    assert create_response.status_code == (200 if partial else 302)
    assert created_range.ident == range_record.ident + 1
    assert created_range.since == 1_200
    assert created_range.till == 1_440

    if partial:
        saved_content = create_response.content.decode()
        assert "20:00–24:00" in saved_content
        assert "id=\"ranges-list\" hx-swap-oob=\"outerHTML\"" in saved_content
        assert "id=\"ranges-message\"" in saved_content
        assert "data-dialog-panel" not in saved_content

    else:
        assert create_response.url == url

    updated = ranges_payload["updated"]
    update_response = client.post(
        url,
        {
            "__submit": "range",
            "range": f"{range_record.pk}",
            "range-weekday": f"{updated["weekday"]}",
            "range-since": updated["since"],
            "range-till": updated["till"],
            "range-session_rule": f"{session_rule_record.pk}",
        },
        **ajax_headers,
    )
    range_record.refresh_from_db()

    assert update_response.status_code == (200 if partial else 302)
    assert range_record.since == 840
    assert range_record.till == 1_140
    assert range_record.apply is False


@pytest.mark.parametrize("partial", [False, True], ids=["ordinary", "ajax"])
def test_ranges_keep_invalid_values_in_the_dialog_and_cancel_without_saving(
    request_client: Callable[..., Client], user_create: Callable[..., User],
    limits_record: Limits, range_record: Range, partial: bool,
) -> None:
    client = request_client(user=user_create(attributes={"is_staff": True}))
    headers = {"HTTP_HX_REQUEST": "true", "HTTP_HX_TRIGGER": "range-save"} if partial else {}
    original_values = (range_record.since, range_record.till, range_record.apply)

    response = client.post(_ranges_url(limits_record), {
        "__submit": "range", "range": range_record.pk,
        "range-weekday": range_record.weekday, "range-since": "25:00", "range-till": "24:00",
        "range-session_rule": range_record.session_rule_id,
    }, **headers)
    content = response.content.decode()
    range_record.refresh_from_db()

    assert response.status_code == 200
    assert "id=\"range-save\" data-dialog-panel" in content
    assert "Enter time as HH:MM." in content
    assert "value=\"25:00\"" in content
    assert "value=\"24:00\"" in content
    assert (range_record.since, range_record.till, range_record.apply) == original_values

    cancel_headers = {"HTTP_HX_REQUEST": "true", "HTTP_HX_TRIGGER": "range-cancel"} if partial else {}
    cancelled = client.get(_ranges_url(limits_record), **cancel_headers)
    range_record.refresh_from_db()

    assert cancelled.status_code == 200
    assert "id=\"range-save\"" not in cancelled.content.decode()
    assert (range_record.since, range_record.till, range_record.apply) == original_values


@pytest.mark.parametrize("partial", [False, True], ids=["ordinary", "ajax"])
def test_ranges_save_assigned_template_as_a_new_version_without_changing_accounts(
    request_client: Callable[..., Client], user_create: Callable[..., User],
    computer_record: Computer, limits_template_record: LimitsTemplate, range_record: Range, partial: bool,
) -> None:
    client = request_client(user=user_create(attributes={"is_staff": True}))
    source_limits = limits_template_record.current_limits
    account = computer_record.accounts.get()
    account.limits = source_limits
    account.save(update_fields=("limits", "updated"))
    headers = {"HTTP_HX_REQUEST": "true", "HTTP_HX_TRIGGER": "range-save"} if partial else {}

    response = client.post(_ranges_url(source_limits), {
        "__submit": "range", "range": range_record.pk, "range-apply": "on",
        "range-weekday": range_record.weekday, "range-since": "14:00", "range-till": "19:00",
        "range-session_rule": range_record.session_rule_id,
    }, **headers)
    limits_template_record.refresh_from_db()
    account.refresh_from_db()
    range_record.refresh_from_db()
    updated = limits_template_record.current_limits.ranges.get(ident=range_record.ident)
    target_url = _ranges_url(limits_template_record.current_limits)

    assert response.status_code == (204 if partial else 302)
    assert response.headers["HX-Redirect" if partial else "Location"] == target_url
    assert limits_template_record.current_limits_id != source_limits.pk
    assert account.limits_id == source_limits.pk
    assert (range_record.since, range_record.till) == (900, 1200)
    assert (updated.since, updated.till) == (840, 1140)
