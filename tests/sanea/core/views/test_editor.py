"""All model editors preserve the same dialog and ordinary form contract."""

from collections.abc import Callable

import pytest
from django.test import Client
from django.urls import reverse

from sanea.core.models import AppRule, Computer, LimitsTemplate, Person, PrcExclusion, Range, SessionRule, User


@pytest.mark.parametrize("ajax", [False, True], ids=["ordinary", "ajax"])
@pytest.mark.parametrize("section, editor_name, reference_name, form_prefix", [
    ("accounts", "account", "account", "account"),
    ("app_rules", "app-rule", "app_rule", "app_rule"),
    ("limits", "limits", "limits", "limits"),
    ("people", "person", "person", "person"),
    ("ranges", "range", "range", "range"),
    ("session_rules", "session-rule", "rule", "rule"),
    ("ignored_processes", "ignored-process", "exclusion", "exclusion"),
])
def test_editors_keep_form_actions_references_and_dialog_controls(
    request_client: Callable[..., Client], user_create: Callable[..., User],
    computer_record: Computer, app_rule_record: AppRule, limits_template_record: LimitsTemplate,
    person_record: Person, range_record: Range, session_rule_record: SessionRule, ignored_process_record: PrcExclusion,
    section: str, editor_name: str, reference_name: str, form_prefix: str, ajax: bool,
) -> None:
    account = computer_record.accounts.get()
    route, arguments, record, fragment = {
        "accounts": ("accounts", (), account, ""),
        "app_rules": (
            "app_rules", (app_rule_record.session_rule.limits_id, app_rule_record.session_rule_id), app_rule_record, "",
        ),
        "limits": ("limits", (), limits_template_record, ""),
        "people": ("people", (), person_record, ""),
        "ranges": ("ranges", (range_record.limits_id,), range_record, ""),
        "session_rules": ("session_rules", (session_rule_record.limits_id,), session_rule_record, ""),
        "ignored_processes": ("limits", (), ignored_process_record, "#ignored-processes"),
    }[section]
    url = reverse(f"core:{route}", args=arguments)
    client = request_client(user=user_create(attributes={"is_staff": True}))
    headers = {"HTTP_HX_REQUEST": "true", "HTTP_HX_TRIGGER": f"{editor_name}-edit-{record.pk}"} if ajax else {}

    response = client.get(url, {reference_name: record.pk}, **headers)
    content = response.content.decode()

    assert response.status_code == 200
    assert f'id="{editor_name}-dialog-title"' in content
    assert f'id="{editor_name}-save" data-dialog-panel method="post" action="{url}{fragment}"' in content
    assert f'hx-post="{url}" hx-target="#{editor_name}-editor" hx-swap="innerHTML"' in content
    assert "hx-disabled-elt=\"find button[type='submit']\"" in content
    assert f'<input type="hidden" name="{reference_name}" value="{record.pk}">' in content
    assert 'name="csrfmiddlewaretoken"' in content
    assert f'id="{editor_name}-cancel" href="{url}{fragment}" data-dialog-close' in content
    assert f'type="submit" name="__submit" value="{form_prefix}"' in content
