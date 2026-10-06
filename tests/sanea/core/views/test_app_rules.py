"""Tests for application rule management."""

from typing import Any
from collections.abc import Callable

from django.urls import reverse
from django.test import Client

from sanea.core.models import AppRule, Limits, SessionRule, User


def _app_rules_url(limits: Limits, session_rule: SessionRule) -> str:
    return reverse("core:app_rules", kwargs={"limits_pk": limits.pk, "rule_pk": session_rule.pk})


def test_app_rules_requires_management_user(
    request_client: Callable[..., Client],
    user_create: Callable[..., User],
    limits_record: Limits,
    session_rule_record: SessionRule,
) -> None:
    url = _app_rules_url(limits_record, session_rule_record)
    anonymous_response = request_client().get(url)
    regular_response = request_client(user=user_create()).get(url)

    assert anonymous_response.status_code == 302
    assert anonymous_response.url.startswith(reverse("core:sign_in"))
    assert regular_response.status_code == 403


def test_app_rules_list_session_members(
    request_client: Callable[..., Client],
    user_create: Callable[..., User],
    limits_record: Limits,
    session_rule_record: SessionRule,
    app_rule_record: AppRule,
) -> None:
    staff_user = user_create(attributes={"is_staff": True})

    response = request_client(user=staff_user).get(
        _app_rules_url(limits_record, session_rule_record)
    )
    content = response.content.decode()

    assert response.status_code == 200
    assert session_rule_record.name in content
    assert app_rule_record.name in content
    assert app_rule_record.prc_name in content
    assert "id=\"app-rule-add\"" in content
    assert f"id=\"app-rule-edit-{app_rule_record.pk}\"" in content


def test_app_rules_ajax_create_and_update(
    request_client: Callable[..., Client],
    user_create: Callable[..., User],
    limits_record: Limits,
    session_rule_record: SessionRule,
    app_rule_record: AppRule,
    app_rules_payload: dict[str, Any],
) -> None:
    staff_user = user_create(attributes={"is_staff": True})
    client = request_client(user=staff_user)
    url = _app_rules_url(limits_record, session_rule_record)
    ajax_headers = {
        "HTTP_HX_REQUEST": "true",
        "HTTP_HX_TRIGGER": "app-rule-save",
    }
    created = app_rules_payload["created"]

    create_response = client.post(
        url,
        {
            "__submit": "app_rule",
            "app_rule": "new",
            "app_rule-name": created["name"],
            "app_rule-apply": "on",
            "app_rule-max_launches": f"{created["max_launches"]}",
            "app_rule-max_time": f"{created["max_time"]}",
            "app_rule-exe": created["exe"],
            "app_rule-exe_match": created["exe_match"],
            "app_rule-wnd_title": created["wnd_title"],
            "app_rule-wnd_title_match": created["wnd_title_match"],
        },
        **ajax_headers,
    )
    created_rule = AppRule.objects.get(
        session_rule=session_rule_record,
        name=created["name"],
    )

    assert create_response.status_code == 200
    assert created_rule.ident == app_rule_record.ident + 1
    assert "hx-swap-oob=\"outerHTML\"" in create_response.content.decode()

    update_response = client.post(
        url,
        {
            "__submit": "app_rule",
            "app_rule": f"{app_rule_record.pk}",
            "app_rule-name": app_rules_payload["renamed"]["name"],
            "app_rule-max_launches": f"{app_rule_record.max_launches}",
            "app_rule-max_time": f"{app_rule_record.max_time}",
            "app_rule-prc_name": app_rule_record.prc_name,
            "app_rule-prc_name_match": app_rule_record.prc_name_match,
        },
        **ajax_headers,
    )
    app_rule_record.refresh_from_db()

    assert update_response.status_code == 200
    assert app_rule_record.name == app_rules_payload["renamed"]["name"]
    assert app_rule_record.apply is False


def test_app_rule_accepts_time_limit_without_launch_limit(
    request_client: Callable[..., Client],
    user_create: Callable[..., User],
    limits_record: Limits,
    session_rule_record: SessionRule,
) -> None:
    staff_user = user_create(attributes={"is_staff": True})
    response = request_client(user=staff_user).post(
        _app_rules_url(limits_record, session_rule_record),
        {
            "__submit": "app_rule",
            "app_rule": "new",
            "app_rule-name": "Time only",
            "app_rule-apply": "on",
            "app_rule-max_launches": "",
            "app_rule-max_time": "1800",
            "app_rule-prc_name": "browser",
            "app_rule-prc_name_match": "exact",
        },
        HTTP_HX_REQUEST="true",
        HTTP_HX_TRIGGER="app-rule-save",
    )

    assert response.status_code == 200
    created = AppRule.objects.get(name="Time only")
    assert created.max_launches is None
    assert created.max_time == 1800
