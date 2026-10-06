"""Tests for session rule management."""

from typing import Any
from collections.abc import Callable

from django.urls import reverse
from django.test import Client

from sanea.core.models import Limits, SessionRule, Computer, LimitsTemplate, User


def test_session_rules_requires_management_user(
    request_client: Callable[..., Client],
    user_create: Callable[..., User],
    limits_record: Limits,
) -> None:
    url = reverse("core:session_rules", kwargs={"limits_pk": limits_record.pk})
    anonymous_response = request_client().get(url)
    regular_response = request_client(user=user_create()).get(url)

    assert anonymous_response.status_code == 302
    assert anonymous_response.url.startswith(reverse("core:sign_in"))
    assert regular_response.status_code == 403


def test_session_rules_list_limits_members(
    request_client: Callable[..., Client],
    user_create: Callable[..., User],
    limits_record: Limits,
    session_rule_record: SessionRule,
) -> None:
    staff_user = user_create(attributes={"is_staff": True})

    response = request_client(user=staff_user).get(
        reverse("core:session_rules", kwargs={"limits_pk": limits_record.pk})
    )
    content = response.content.decode()

    assert response.status_code == 200
    assert limits_record.name in content
    assert session_rule_record.name in content
    assert "id=\"session-rule-add\"" in content
    assert f"id=\"session-rule-edit-{session_rule_record.pk}\"" in content


def test_session_rules_ajax_create_and_update(
    request_client: Callable[..., Client],
    user_create: Callable[..., User],
    limits_record: Limits,
    session_rule_record: SessionRule,
    session_rules_payload: dict[str, Any],
) -> None:
    staff_user = user_create(attributes={"is_staff": True})
    client = request_client(user=staff_user)
    url = reverse("core:session_rules", kwargs={"limits_pk": limits_record.pk})
    ajax_headers = {
        "HTTP_HX_REQUEST": "true",
        "HTTP_HX_TRIGGER": "session-rule-save",
    }
    created = session_rules_payload["created"]

    create_response = client.post(
        url,
        {
            "__submit": "rule",
            "rule": "new",
            "rule-name": created["name"],
            "rule-apply": "on",
            "rule-max_sessions": f"{created["max_sessions"]}",
            "rule-max_duration": f"{created["max_duration"]}",
            "rule-break_duration": f"{created["break_duration"]}",
        },
        **ajax_headers,
    )
    created_rule = SessionRule.objects.get(limits=limits_record, name=created["name"])

    assert create_response.status_code == 200
    assert created_rule.ident == session_rule_record.ident + 1
    assert "hx-swap-oob=\"outerHTML\"" in create_response.content.decode()

    update_response = client.post(
        url,
        {
            "__submit": "rule",
            "rule": f"{session_rule_record.pk}",
            "rule-name": session_rules_payload["renamed"]["name"],
            "rule-max_sessions": f"{session_rule_record.max_sessions}",
            "rule-max_duration": f"{session_rule_record.max_duration}",
            "rule-break_duration": f"{session_rule_record.break_duration}",
        },
        **ajax_headers,
    )
    session_rule_record.refresh_from_db()

    assert update_response.status_code == 200
    assert session_rule_record.name == session_rules_payload["renamed"]["name"]
    assert session_rule_record.apply is False


def test_template_edit_forks_snapshot_and_redirects_editor(
    request_client: Callable[..., Client],
    user_create: Callable[..., User],
    computer_record: Computer,
    limits_template_record: LimitsTemplate,
    session_rule_record: SessionRule,
    session_rules_payload: dict[str, Any],
) -> None:
    staff_user = user_create(attributes={"is_staff": True})
    account = computer_record.accounts.get()
    account.limits = limits_template_record.current_limits
    account.save(update_fields=("limits", "updated"))
    source_limits = limits_template_record.current_limits
    created = session_rules_payload["created"]

    response = request_client(user=staff_user).post(
        reverse("core:session_rules", kwargs={"limits_pk": source_limits.pk}),
        {
            "__submit": "rule",
            "rule": "new",
            "rule-name": created["name"],
            "rule-apply": "on",
            "rule-max_sessions": f"{created["max_sessions"]}",
            "rule-max_duration": f"{created["max_duration"]}",
            "rule-break_duration": f"{created["break_duration"]}",
        },
        HTTP_HX_REQUEST="true",
        HTTP_HX_TRIGGER="session-rule-save",
    )
    limits_template_record.refresh_from_db()
    account.refresh_from_db()

    assert response.status_code == 204
    assert limits_template_record.current_limits_id != source_limits.pk
    assert account.limits_id == source_limits.pk
    assert response.headers["HX-Redirect"].endswith(
        reverse("core:session_rules", kwargs={"limits_pk": limits_template_record.current_limits_id})
    )
