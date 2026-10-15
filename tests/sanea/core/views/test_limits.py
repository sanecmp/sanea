"""Tests for limits set management."""

from typing import Any
from collections.abc import Callable
import re

import pytest
from django.urls import reverse
from django.test import Client

from sanea.core.models import Account, Computer, Limits, LimitsTemplate, Person, Range, SessionRule, User


def test_limits_requires_management_user(request_client: Callable[..., Client], user_create: Callable[..., User]) -> None:
    anonymous_response = request_client().get(reverse("core:limits"))
    regular_response = request_client(user=user_create()).get(reverse("core:limits"))

    assert anonymous_response.status_code == 302
    assert anonymous_response.url.startswith(reverse("core:sign_in"))
    assert regular_response.status_code == 403


def test_limits_lists_templates(
    request_client: Callable[..., Client],
    user_create: Callable[..., User],
    limits_template_record: LimitsTemplate,
) -> None:
    staff_user = user_create(attributes={"is_staff": True})

    response = request_client(user=staff_user).get(reverse("core:limits"))
    content = response.content.decode()

    assert response.status_code == 200
    assert limits_template_record.name in content
    assert "<table class=\"table align-top mb-0\">" in content
    template_list = content.split("id=\"limits-list\"", 1)[1].split("</table>", 1)[0]
    assert "<th scope=\"col\">Updated</th>" not in template_list
    assert '<th scope="col" class="text-center">Sessions</th>' in template_list
    assert '<th scope="col" class="text-center">Ranges</th>' in template_list
    assert '<th scope="col">Schedule</th>' not in template_list
    assert "id=\"limits-add\"" in content
    assert f"id=\"limits-edit-{limits_template_record.pk}\"" in content
    assert "limits-edit-name-" not in content
    assert f"<td>{limits_template_record.name}</td>" in content
    assert "id=\"limits-dialog\"" in content
    assert "data-editor-dialog" in content
    assert "id=\"limits-save\"" not in content
    assert f"aria-label=\"Edit: {limits_template_record.name}\"" in content
    assert f"aria-label=\"Distribute template: {limits_template_record.name}\"" in content
    assert f"id=\"limits-apply-{limits_template_record.pk}\"" in content
    assert "<use href=\"#icon-plus\">" in content
    assert "<use href=\"#icon-edit\">" in content
    assert "<use href=\"#icon-distribute\">" in content
    assert "<use href=\"#icon-copy\">" not in content


@pytest.mark.parametrize("partial", [False, True], ids=["ordinary", "ajax"])
@pytest.mark.parametrize("creating", [False, True], ids=["edit", "add"])
def test_limits_adds_and_edits_in_the_same_dialog(
    request_client: Callable[..., Client], user_create: Callable[..., User],
    limits_template_record: LimitsTemplate, partial: bool, creating: bool,
) -> None:
    client = request_client(user=user_create(attributes={"is_staff": True}))
    reference = "new" if creating else f"{limits_template_record.pk}"
    trigger = "limits-add" if creating else f"limits-edit-{limits_template_record.pk}"
    headers = {"HTTP_HX_REQUEST": "true", "HTTP_HX_TRIGGER": trigger} if partial else {}

    response = client.get(reverse("core:limits"), {"limits": reference}, **headers)
    content = response.content.decode()

    assert response.status_code == 200
    assert "id=\"limits-dialog-title\"" in content
    assert "id=\"limits-save\" data-dialog-panel" in content
    assert "name=\"limits-name\"" in content
    assert "data-dialog-close" in content
    assert "id=\"ignored-process-save\"" not in content
    editor_content = content.split("id=\"limits-save\"", 1)[1].split("</form>", 1)[0]
    assert "limits-apply-" not in editor_content


def test_limits_lists_people_and_latest_accounts_by_name(
    request_client: Callable[..., Client], user_create: Callable[..., User],
    limits_template_record: LimitsTemplate, person_record: Person, computer_record: Computer,
) -> None:
    client = request_client(user=user_create(attributes={"is_staff": True}))
    person_record.limits_tpl = limits_template_record
    person_record.save(update_fields=("limits_tpl", "updated"))
    other_person = Person.objects.create(name="Another synthetic person", limits_tpl=limits_template_record)
    account = computer_record.accounts.get()
    account.name = "Shared synthetic name"
    account.person = person_record
    account.limits = limits_template_record.current_limits
    account.save()
    other_computer = Computer.objects.create(hostname="another-synthetic-pc", name="Another synthetic computer")
    other_account = Account.objects.create(
        computer=other_computer, uid=2001, login=account.login, name=account.name,
        person=other_person, limits=limits_template_record.current_limits,
    )
    Account.objects.create(
        computer=computer_record, uid=2002, login="old", name="Older assignment",
        person=person_record, limits=Limits.objects.create(name="Previous synthetic version"),
    )

    response = client.get(reverse("core:limits"))
    content = response.content.decode()
    row = next(row for row in re.findall(r"<tr>(.*?)</tr>", content, re.S) if limits_template_record.name in row)

    assert response.status_code == 200
    assert f"<li>{person_record.name}</li>" in row
    assert f"<li>{other_person.name}</li>" in row
    assert row.count("<ul class=\"ps-3 mb-0\">") == 2
    assert "list-unstyled" not in row
    ordered_names = sorted((person_record.name, other_person.name))
    assert row.index(f"<li>{ordered_names[0]}</li>") < row.index(f"<li>{ordered_names[1]}</li>")
    assert f"<li>{account.name} · {computer_record.get_display_name()}</li>" in row
    assert f"<li>{other_account.name} · {other_computer.get_display_name()}</li>" in row
    assert "Older assignment" not in row


def test_limits_counts_each_templates_current_rules_and_ranges(
    request_client: Callable[..., Client], user_create: Callable[..., User],
    limits_template_record: LimitsTemplate, range_record: Range,
) -> None:
    client = request_client(user=user_create(attributes={"is_staff": True}))
    previous = limits_template_record.current_limits
    current = previous.clone("Current synthetic version")
    limits_template_record.current_limits = current
    limits_template_record.save()
    second_rule = SessionRule.objects.create(
        limits=current, name="Another synthetic rule", ident=range_record.session_rule.ident + 1,
    )

    for weekday in (5, 6):
        Range.objects.create(
            limits=current, ident=range_record.ident + weekday, weekday=weekday,
            since=0, till=60, session_rule=second_rule,
        )

    other_template = LimitsTemplate.objects.create(name="Another synthetic template", current_limits=previous)
    empty_template = LimitsTemplate.objects.create(name="Empty synthetic template", current_limits=Limits.objects.create())

    response = client.get(reverse("core:limits"))
    content = response.content.decode()
    rows = re.findall(r"<tr>(.*?)</tr>", content, re.S)

    assert response.status_code == 200

    expectations = ((limits_template_record, 2, 3), (other_template, 1, 1), (empty_template, 0, 0))

    for template, rule_count, range_count in expectations:
        row = next(row for row in rows if f"<td>{template.name}</td>" in row)
        rule_url = reverse("core:session_rules", args=(template.current_limits_id,))
        range_url = reverse("core:ranges", args=(template.current_limits_id,))
        assert re.search(rf'<a\b[^>]*href="{re.escape(rule_url)}"[^>]*>\s*{rule_count}\s*</a>', row)
        assert re.search(rf'<a\b[^>]*href="{re.escape(range_url)}"[^>]*>\s*{range_count}\s*</a>', row)
        assert f'aria-label="Session rules: {rule_count}"' in row
        assert f'aria-label="Schedule ranges: {range_count}"' in row


def test_limits_ajax_create_and_rename(
    request_client: Callable[..., Client],
    user_create: Callable[..., User],
    limits_template_record: LimitsTemplate,
    limits_payload: dict[str, Any],
) -> None:
    staff_user = user_create(attributes={"is_staff": True})
    client = request_client(user=staff_user)
    ajax_headers = {
        "HTTP_HX_REQUEST": "true",
        "HTTP_HX_TRIGGER": "limits-save",
    }

    create_response = client.post(
        reverse("core:limits"),
        {
            "__submit": "limits",
            "limits": "new",
            "limits-name": limits_payload["created"]["name"],
        },
        **ajax_headers,
    )
    assert create_response.status_code == 200
    created = LimitsTemplate.objects.get(**limits_payload["created"])
    assert created.current_limits.name == limits_payload["created"]["name"]
    assert "hx-swap-oob=\"outerHTML\"" in create_response.content.decode()
    assert "id=\"limits-message\"" in create_response.content.decode()
    assert "data-dialog-panel" not in create_response.content.decode()
    assert "id=\"ignored-processes-list\"" not in create_response.content.decode()

    rename_response = client.post(
        reverse("core:limits"),
        {
            "__submit": "limits",
            "limits": f"{limits_template_record.pk}",
            "limits-name": limits_payload["renamed"]["name"],
        },
        **ajax_headers,
    )
    limits_template_record.refresh_from_db()

    assert rename_response.status_code == 200
    assert limits_template_record.name == limits_payload["renamed"]["name"]
    assert "data-dialog-panel" not in rename_response.content.decode()


@pytest.mark.parametrize("partial", [False, True], ids=["ordinary", "ajax"])
def test_limits_edits_default_recipients_without_changing_account_limits(
    request_client: Callable[..., Client], user_create: Callable[..., User],
    limits_template_record: LimitsTemplate, person_record: Person, computer_record: Computer, partial: bool,
) -> None:
    client = request_client(user=user_create(attributes={"is_staff": True}))
    account = computer_record.accounts.get()
    account.person = person_record
    account.save(update_fields=("person", "updated"))
    previous_limits_id = account.limits_id
    ajax_headers = {"HTTP_HX_REQUEST": "true", "HTTP_HX_TRIGGER": "limits-save"} if partial else {}
    payload = {
        "__submit": "limits", "limits": limits_template_record.pk,
        "limits-name": limits_template_record.name, "limits-people": [person_record.pk],
    }

    response = client.post(reverse("core:limits"), payload, **ajax_headers)
    person_record.refresh_from_db()
    account.refresh_from_db()

    assert response.status_code == (200 if partial else 302)
    assert person_record.limits_tpl == limits_template_record
    assert account.limits_id == previous_limits_id

    editor = client.get(reverse("core:limits"), {"limits": limits_template_record.pk})

    assert "Default template for" in editor.content.decode()
    assert "checked" in editor.content.decode()
    assert f"id=\"limits-apply-{limits_template_record.pk}\"" in editor.content.decode()

    payload["limits-name"] = ""
    payload["limits-people"] = []
    invalid = client.post(reverse("core:limits"), payload, **ajax_headers)
    person_record.refresh_from_db()

    assert invalid.status_code == 200
    assert "This field is required." in invalid.content.decode()
    assert "data-dialog-panel" in invalid.content.decode()
    assert "name=\"limits-name\"" in invalid.content.decode()
    assert person_record.limits_tpl == limits_template_record

    payload["limits-name"] = limits_template_record.name
    cleared = client.post(reverse("core:limits"), payload, **ajax_headers)
    person_record.refresh_from_db()
    account.refresh_from_db()

    assert cleared.status_code == (200 if partial else 302)
    assert person_record.limits_tpl is None
    assert account.limits_id == previous_limits_id


@pytest.mark.parametrize("partial", [False, True], ids=["ordinary", "ajax"])
def test_limits_explicit_application_updates_only_selected_eligible_accounts(
    request_client: Callable[..., Client], user_create: Callable[..., User],
    limits_template_record: LimitsTemplate, person_record: Person, computer_record: Computer, partial: bool,
) -> None:
    client = request_client(user=user_create(attributes={"is_staff": True}))
    person_record.limits_tpl = limits_template_record
    person_record.save(update_fields=("limits_tpl", "updated"))
    account = computer_record.accounts.get()
    account.person = person_record
    account.save(update_fields=("person", "updated"))
    other_person = Person.objects.create(name="Another synthetic person", limits_tpl=limits_template_record)
    untouched = Account.objects.create(computer=computer_record, uid=2001, login="untouched", person=other_person)
    foreign = Account.objects.create(computer=computer_record, uid=2002, login="foreign")
    previous_limits_id = account.limits_id
    ajax_headers = {"HTTP_HX_REQUEST": "true", "HTTP_HX_TRIGGER": "limits-apply-save"} if partial else {}
    get_headers = {"HTTP_HX_REQUEST": "true", "HTTP_HX_TRIGGER": f"limits-apply-{limits_template_record.pk}"} if partial else {}

    preview = client.get(reverse("core:limits"), {"limits": limits_template_record.pk, "apply": "1"}, **get_headers)
    content = preview.content.decode()
    account.refresh_from_db()

    assert preview.status_code == 200
    assert "id=\"limits-dialog-title\">Distribute template</h2>" in content
    assert "id=\"limits-apply-save\" data-dialog-panel" in content
    assert "This replaces the selected accounts' current limits." in content
    assert account.computer.get_display_name() in content
    assert "untouched" in content
    assert "foreign" not in content
    assert "checked" in content
    assert account.limits_id == previous_limits_id

    cancel_headers = {"HTTP_HX_REQUEST": "true", "HTTP_HX_TRIGGER": "limits-apply-cancel"} if partial else {}
    cancelled = client.get(reverse("core:limits"), **cancel_headers)
    account.refresh_from_db()

    assert cancelled.status_code == 200
    assert account.limits_id == previous_limits_id

    payload = {
        "__submit": "propagation", "limits": limits_template_record.pk,
        "apply_template": "1", "propagation-accounts": [foreign.pk],
    }
    invalid = client.post(reverse("core:limits"), payload, **ajax_headers)
    account.refresh_from_db()
    foreign.refresh_from_db()

    assert invalid.status_code == 200
    assert "Select a valid choice." in invalid.content.decode()
    assert "id=\"limits-apply-save\" data-dialog-panel" in invalid.content.decode()
    assert account.limits_id == previous_limits_id
    assert foreign.limits_id is None

    payload["propagation-accounts"] = [account.pk]
    applied = client.post(reverse("core:limits"), payload, **ajax_headers)
    account.refresh_from_db()
    untouched.refresh_from_db()

    assert applied.status_code == (200 if partial else 302)
    assert account.limits == limits_template_record.current_limits
    assert untouched.limits_id is None

    if partial:
        assert "id=\"limits-message\"" in applied.content.decode()
        assert "data-dialog-panel" not in applied.content.decode()


def test_limits_application_without_accounts_links_back_to_template_settings(
    request_client: Callable[..., Client], user_create: Callable[..., User], limits_template_record: LimitsTemplate,
) -> None:
    client = request_client(user=user_create(attributes={"is_staff": True}))

    response = client.get(reverse("core:limits"), {"limits": limits_template_record.pk, "apply": "1"})
    content = response.content.decode()

    assert response.status_code == 200
    assert "No accounts are linked to this template's people." in content
    assert "data-dialog-panel" in content
    assert "data-dialog-close" in content
    assert f"id=\"limits-edit-recipients-{limits_template_record.pk}\"" in content
    assert "id=\"limits-apply-save\"" not in content


def test_limits_creation_can_move_recipients_without_applying_account_limits(
    request_client: Callable[..., Client], user_create: Callable[..., User],
    limits_template_record: LimitsTemplate, person_record: Person, computer_record: Computer,
) -> None:
    client = request_client(user=user_create(attributes={"is_staff": True}))
    person_record.limits_tpl = limits_template_record
    person_record.save(update_fields=("limits_tpl", "updated"))
    account = computer_record.accounts.get()
    account.person = person_record
    account.save(update_fields=("person", "updated"))
    previous_limits_id = account.limits_id

    response = client.post(reverse("core:limits"), {
        "__submit": "limits", "limits": "new", "limits-name": "New synthetic template",
        "limits-people": [person_record.pk],
    })
    person_record.refresh_from_db()
    account.refresh_from_db()
    template = LimitsTemplate.objects.get(name="New synthetic template")

    assert response.status_code == 302
    assert person_record.limits_tpl == template
    assert not limits_template_record.people.exists()
    assert account.limits_id == previous_limits_id
