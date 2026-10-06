"""Tests for weekly schedule range management."""

from typing import Any
from collections.abc import Callable

from django.urls import reverse
from django.test import Client

from sanea.core.models import Limits, Range, SessionRule, User


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


def test_ranges_list_schedule_intervals(
    request_client: Callable[..., Client],
    user_create: Callable[..., User],
    limits_record: Limits,
    range_record: Range,
) -> None:
    staff_user = user_create(attributes={"is_staff": True})

    response = request_client(user=staff_user).get(_ranges_url(limits_record))
    content = response.content.decode()

    assert response.status_code == 200
    assert "Friday" in content
    assert "15:00–20:00" in content
    assert range_record.session_rule.name in content
    assert "id=\"range-add\"" in content
    assert f"id=\"range-edit-{range_record.pk}\"" in content


def test_ranges_ajax_create_and_update(
    request_client: Callable[..., Client],
    user_create: Callable[..., User],
    limits_record: Limits,
    session_rule_record: SessionRule,
    range_record: Range,
    ranges_payload: dict[str, Any],
) -> None:
    staff_user = user_create(attributes={"is_staff": True})
    client = request_client(user=staff_user)
    url = _ranges_url(limits_record)
    ajax_headers = {
        "HTTP_HX_REQUEST": "true",
        "HTTP_HX_TRIGGER": "range-save",
    }
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

    assert create_response.status_code == 200
    assert created_range.ident == range_record.ident + 1
    assert created_range.since == 1_200
    assert created_range.till == 1_440
    assert "20:00–24:00" in create_response.content.decode()

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

    assert update_response.status_code == 200
    assert range_record.since == 840
    assert range_record.till == 1_140
    assert range_record.apply is False
