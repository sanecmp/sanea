"""Tests for session rule management."""

from typing import Any
from collections.abc import Callable
import re

import pytest
from django.urls import reverse
from django.test import Client

from sanea.core.models import AppRule, Limits, SessionRule, Computer, LimitsTemplate, User


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


@pytest.mark.parametrize(
    "applied, status, icon",
    [(True, "Limits applied", "check"), (False, "Limits not applied", "ban")],
)
def test_session_rules_list_limits_members(
    request_client: Callable[..., Client],
    user_create: Callable[..., User],
    limits_record: Limits,
    session_rule_record: SessionRule,
    app_rule_record: AppRule,
    applied: bool,
    status: str,
    icon: str,
) -> None:
    staff_user = user_create(attributes={"is_staff": True})
    session_rule_record.apply = applied
    session_rule_record.save(update_fields=("apply", "updated"))

    response = request_client(user=staff_user).get(
        reverse("core:session_rules", kwargs={"limits_pk": limits_record.pk})
    )
    content = response.content.decode()

    assert response.status_code == 200
    assert limits_record.name in content
    assert session_rule_record.name in content
    assert "id=\"session-rule-add\"" in content
    assert f"id=\"session-rule-edit-{session_rule_record.pk}\"" in content
    assert "←" not in content
    assert '<nav aria-label="Breadcrumbs">' in content
    assert '<use href="#icon-plus">' in content
    assert '<use href="#icon-edit">' in content
    assert '<th scope="col" class="text-center">Limits</th>' in content
    assert '<th scope="col" class="text-center">Maximum sessions</th>' in content
    assert f'<td class="small text-body-secondary text-center">{session_rule_record.max_sessions}</td>' in content
    assert f'role="img" title="{status}" aria-label="{status}"' in content
    assert f'<use href="#icon-{icon}">' in content
    assert "badge" not in content
    assert 'id="session-rule-dialog"' in content
    assert "data-editor-dialog" in content
    assert 'id="session-rule-save"' not in content
    application_link = re.search(
        r'<td class="small text-center">\s*(<a\b.*?</a>)\s*</td>', content, re.S,
    )

    assert application_link is not None
    assert f'href="{reverse("core:app_rules", args=(limits_record.pk, session_rule_record.pk))}"' in application_link.group(1)
    assert 'aria-label="Application rules: 1"' in application_link.group(1)
    assert re.sub(r"<[^>]+>", "", application_link.group(1)).strip() == "1"


@pytest.mark.parametrize("partial", [False, True], ids=["ordinary", "ajax"])
@pytest.mark.parametrize("creating", [False, True], ids=["edit", "add"])
def test_session_rules_add_and_edit_in_one_dialog_with_quotas_on_the_same_row(
    request_client: Callable[..., Client], user_create: Callable[..., User],
    limits_record: Limits, session_rule_record: SessionRule, partial: bool, creating: bool,
) -> None:
    client = request_client(user=user_create(attributes={"is_staff": True}))
    reference = "new" if creating else f"{session_rule_record.pk}"
    trigger = "session-rule-add" if creating else f"session-rule-edit-{session_rule_record.pk}"
    headers = {"HTTP_HX_REQUEST": "true", "HTTP_HX_TRIGGER": trigger} if partial else {}
    url = reverse("core:session_rules", kwargs={"limits_pk": limits_record.pk})

    response = client.get(url, {"rule": reference}, **headers)
    content = response.content.decode()
    rows = re.split(r'<div\s+class="row gx-3">', content)
    quota_row = next(row for row in rows if 'id="id_rule-max_sessions"' in row)

    assert response.status_code == 200
    assert 'id="session-rule-dialog-title"' in content
    assert 'id="session-rule-save" data-dialog-panel' in content
    assert "data-dialog-close" in content
    assert 'id="id_rule-max_duration"' in quota_row
    assert 'id="id_rule-break_duration"' in quota_row
    assert 'id="id_rule-name"' not in quota_row
    assert 'id="id_rule-apply"' not in quota_row

    if not creating:
        assert f'value="{session_rule_record.max_sessions}"' in quota_row
        assert f'value="{session_rule_record.max_duration}"' in quota_row


@pytest.mark.parametrize("partial", [False, True], ids=["ordinary", "ajax"])
def test_session_rules_create_and_update(
    request_client: Callable[..., Client],
    user_create: Callable[..., User],
    limits_record: Limits,
    session_rule_record: SessionRule,
    session_rules_payload: dict[str, Any],
    partial: bool,
) -> None:
    staff_user = user_create(attributes={"is_staff": True})
    client = request_client(user=staff_user)
    url = reverse("core:session_rules", kwargs={"limits_pk": limits_record.pk})
    ajax_headers = {
        "HTTP_HX_REQUEST": "true",
        "HTTP_HX_TRIGGER": "session-rule-save",
    } if partial else {}
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

    assert create_response.status_code == (200 if partial else 302)
    assert created_rule.ident == session_rule_record.ident + 1

    if partial:
        saved_content = create_response.content.decode()
        assert 'id="session-rules-list" hx-swap-oob="outerHTML"' in saved_content
        assert 'id="session_rules-message"' in saved_content
        assert "data-dialog-panel" not in saved_content

    else:
        assert create_response.url == url

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

    assert update_response.status_code == (200 if partial else 302)
    assert session_rule_record.name == session_rules_payload["renamed"]["name"]
    assert session_rule_record.apply is False


@pytest.mark.parametrize("partial", [False, True], ids=["ordinary", "ajax"])
def test_session_rules_template_edit_forks_snapshot_and_redirects_editor(
    request_client: Callable[..., Client],
    user_create: Callable[..., User],
    computer_record: Computer,
    limits_template_record: LimitsTemplate,
    session_rule_record: SessionRule,
    session_rules_payload: dict[str, Any],
    partial: bool,
) -> None:
    staff_user = user_create(attributes={"is_staff": True})
    account = computer_record.accounts.get()
    account.limits = limits_template_record.current_limits
    account.save(update_fields=("limits", "updated"))
    source_limits = limits_template_record.current_limits
    created = session_rules_payload["created"]
    headers = {"HTTP_HX_REQUEST": "true", "HTTP_HX_TRIGGER": "session-rule-save"} if partial else {}

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
        **headers,
    )
    limits_template_record.refresh_from_db()
    account.refresh_from_db()

    assert response.status_code == (204 if partial else 302)
    assert limits_template_record.current_limits_id != source_limits.pk
    assert account.limits_id == source_limits.pk
    assert not source_limits.session_rules.filter(name=created["name"]).exists()
    assert limits_template_record.current_limits.session_rules.filter(name=created["name"]).exists()
    assert response.headers["HX-Redirect" if partial else "Location"] == (
        reverse("core:session_rules", kwargs={"limits_pk": limits_template_record.current_limits_id})
    )


@pytest.mark.parametrize("partial", [False, True], ids=["ordinary", "ajax"])
def test_session_rules_keep_invalid_values_in_the_dialog_and_cancel_without_saving(
    request_client: Callable[..., Client], user_create: Callable[..., User],
    limits_record: Limits, session_rule_record: SessionRule, partial: bool,
) -> None:
    client = request_client(user=user_create(attributes={"is_staff": True}))
    url = reverse("core:session_rules", kwargs={"limits_pk": limits_record.pk})
    headers = {"HTTP_HX_REQUEST": "true", "HTTP_HX_TRIGGER": "session-rule-save"} if partial else {}
    original_values = (session_rule_record.name, session_rule_record.max_duration, session_rule_record.apply)

    response = client.post(url, {
        "__submit": "rule", "rule": session_rule_record.pk,
        "rule-name": "Unsaved edit", "rule-max_sessions": "2", "rule-max_duration": "-1",
        "rule-break_duration": "900",
    }, **headers)
    content = response.content.decode()
    session_rule_record.refresh_from_db()

    assert response.status_code == 200
    assert 'id="session-rule-save" data-dialog-panel' in content
    assert "Ensure this value is greater than or equal to 0." in content
    assert 'value="Unsaved edit"' in content
    assert 'value="-1"' in content
    assert (session_rule_record.name, session_rule_record.max_duration, session_rule_record.apply) == original_values

    cancel_headers = {"HTTP_HX_REQUEST": "true", "HTTP_HX_TRIGGER": "session-rule-cancel"} if partial else {}
    cancelled = client.get(url, **cancel_headers)
    session_rule_record.refresh_from_db()

    assert cancelled.status_code == 200
    assert 'id="session-rule-save"' not in cancelled.content.decode()
    assert (session_rule_record.name, session_rule_record.max_duration, session_rule_record.apply) == original_values


@pytest.mark.parametrize(
    "page, has_template_caption",
    [
        ("session_rules", False),
        ("ranges", False),
        ("app_rules", True),
    ],
)
def test_rule_pages_explain_template_distribution(
    request_client: Callable[..., Client],
    user_create: Callable[..., User],
    computer_record: Computer,
    limits_template_record: LimitsTemplate,
    session_rule_record: SessionRule,
    page: str,
    has_template_caption: bool,
) -> None:
    account = computer_record.accounts.get()
    account.limits = limits_template_record.current_limits
    account.save(update_fields=("limits", "updated"))
    kwargs = {"limits_pk": account.limits_id}

    if page == "app_rules":
        kwargs["rule_pk"] = session_rule_record.pk

    staff_user = user_create(attributes={"is_staff": True})
    response = request_client(user=staff_user).get(reverse(f"core:{page}", kwargs=kwargs))
    content = response.content.decode()

    assert response.status_code == 200
    assert ("Editing template:" in content) is has_template_caption

    if has_template_caption:
        assert re.search(r'<p class="mb-3">\s*Editing template:', content)

    assert f"{limits_template_record.current_limits}" in content
    hint = re.search(r'<div\b[^>]*role="note"[^>]*>(.*?)</div>', content, re.S)

    assert hint is not None
    assert "alert-info" in hint.group(0)
    assert '<use href="#icon-info">' in hint.group(1)
    assert "To update accounts, use “Distribute template” in Limits." in hint.group(1)
    assert "Accounts using this version" not in hint.group(1)
    assert f"{reverse("core:limits")}?limits={limits_template_record.pk}&amp;apply=1" not in content
    assert "alert alert-secondary" not in content
    assert "<details" not in content
    accounts_block = re.search(
        r'<section class="mt-4" aria-labelledby="limits-scope-accounts-title">(.*?)</section>', content, re.S,
    )

    assert accounts_block is not None
    assert 'id="limits-scope-accounts-title"' in accounts_block.group(1)
    assert "Accounts using this version: 1" in accounts_block.group(1)
    assert f"<li>{account.name} · {computer_record.name}</li>" in accounts_block.group(1)
