"""Tests for local account management."""

from collections.abc import Callable

import pytest
from django.urls import reverse
from django.test import Client

from sanea.core.models import Account, Person, Computer, Limits, LimitsTemplate, Range, User


def test_accounts_requires_management_user(request_client: Callable[..., Client], user_create: Callable[..., User]) -> None:
    anonymous_response = request_client().get(reverse("core:accounts"))
    regular_response = request_client(user=user_create()).get(reverse("core:accounts"))

    assert anonymous_response.status_code == 302
    assert anonymous_response.url.startswith(reverse("core:sign_in"))
    assert regular_response.status_code == 403


def test_accounts_lists_reported_records(
    request_client: Callable[..., Client],
    user_create: Callable[..., User],
    computer_record: Computer,
) -> None:
    staff_user = user_create(attributes={"is_staff": True})
    account = Account.objects.get(computer=computer_record)

    response = request_client(user=staff_user).get(reverse("core:accounts"))
    content = response.content.decode()

    assert response.status_code == 200
    assert account.login in content
    assert computer_record.name in content
    assert f"id=\"account-edit-{account.pk}\"" in content
    assert "sanea-mobile-table" in content
    assert "sanea-table-actions" in content
    assert "data-label=\"Monitoring\"" in content
    assert "data-label=\"On computer\"" in content
    assert "Exists" in content
    assert "not an active session" in content
    assert "Add account" not in content


def test_accounts_ajax_updates_sanea_owned_settings(
    request_client: Callable[..., Client],
    user_create: Callable[..., User],
    computer_record: Computer,
    person_record: Person,
) -> None:
    staff_user = user_create(attributes={"is_staff": True})
    client = request_client(user=staff_user)
    account = Account.objects.get(computer=computer_record)

    editor_response = client.get(
        reverse("core:accounts"), {"account": account.pk},
        HTTP_HX_REQUEST="true",
        HTTP_HX_TRIGGER=f"account-edit-{account.pk}",
    )
    assert editor_response.status_code == 200
    assert "name=\"account-person\"" in editor_response.content.decode()

    save_response = client.post(
        reverse("core:accounts"),
        {
            "__submit": "account",
            "account": f"{account.pk}",
            "account-person": f"{person_record.pk}",
            "account-collect": "on",
        },
        HTTP_HX_REQUEST="true",
        HTTP_HX_TRIGGER="account-save",
    )
    account.refresh_from_db()

    assert save_response.status_code == 200
    assert account.person == person_record
    assert account.collect is True
    assert account.apply is False
    assert "hx-swap-oob=\"outerHTML\"" in save_response.content.decode()

def test_accounts_ajax_creates_independent_limits(
    request_client: Callable[..., Client],
    user_create: Callable[..., User],
    computer_record: Computer,
) -> None:
    staff_user = user_create(attributes={"is_staff": True})
    account = Account.objects.get(computer=computer_record)

    response = request_client(user=staff_user).post(
        reverse("core:accounts"),
        {"account": f"{account.pk}", "customize_limits": "1"},
        HTTP_HX_REQUEST="true",
        HTTP_HX_TRIGGER=f"account-limits-customize-{account.pk}",
    )
    account.refresh_from_db()

    assert response.status_code == 200
    assert account.limits is not None
    assert account.limits.name == f"{account.login} @ {computer_record.hostname}"
    assert "Limits:" in response.content.decode()



def test_assigning_person_uses_current_template_snapshot(
    request_client: Callable[..., Client],
    user_create: Callable[..., User],
    computer_record: Computer,
    person_record: Person,
    limits_template_record: LimitsTemplate,
) -> None:
    staff_user = user_create(attributes={"is_staff": True})
    account = Account.objects.get(computer=computer_record)
    person_record.limits_tpl = limits_template_record
    person_record.save(update_fields=("limits_tpl", "updated"))

    response = request_client(user=staff_user).post(
        reverse("core:accounts"),
        {
            "__submit": "account",
            "account": f"{account.pk}",
            "account-person": f"{person_record.pk}",
            "account-collect": "on",
        },
        HTTP_HX_REQUEST="true",
        HTTP_HX_TRIGGER="account-save",
    )
    account.refresh_from_db()

    assert response.status_code == 200
    assert account.limits == limits_template_record.current_limits


@pytest.mark.parametrize("ajax", [False, True])
def test_enabling_without_limits_shows_error_without_saving(
    request_client: Callable[..., Client],
    user_create: Callable[..., User],
    computer_record: Computer,
    ajax: bool,
) -> None:
    account = computer_record.accounts.get()
    account.collect = False
    account.save(update_fields=("collect", "updated"))
    staff_user = user_create(attributes={"is_staff": True})
    headers = {"HTTP_HX_REQUEST": "true", "HTTP_HX_TRIGGER": "account-save"} if ajax else {}

    response = request_client(user=staff_user).post(
        reverse("core:accounts"),
        {"account": f"{account.pk}", "__submit": "account", "account-apply": "on"},
        **headers,
    )
    account.refresh_from_db()
    computer_record.refresh_from_db()

    assert response.status_code == 200
    assert "Configure a limits set before enabling restrictions." in response.content.decode()
    assert account.apply is False
    assert account.collect is False
    assert account.limits_id is None
    assert computer_record.current_config_id is None


@pytest.mark.parametrize("ajax", [False, True])
@pytest.mark.parametrize("confirm", [False, True])
def test_empty_schedule_needs_confirmation_before_activation(
    request_client: Callable[..., Client],
    user_create: Callable[..., User],
    computer_record: Computer,
    limits_record: Limits,
    range_record: Range,
    ajax: bool,
    confirm: bool,
) -> None:
    account = computer_record.accounts.get()
    account.limits = limits_record
    account.collect = False
    account.save(update_fields=("limits", "collect", "updated"))
    range_record.apply = False
    range_record.save(update_fields=("apply", "updated"))
    staff_user = user_create(attributes={"is_staff": True})
    headers = {"HTTP_HX_REQUEST": "true", "HTTP_HX_TRIGGER": "account-save"} if ajax else {}
    data = {
        "account": f"{account.pk}",
        "__submit": "account",
        "account-apply": "on",
        "account-confirm_empty_schedule": "on" if confirm else "",
    }

    response = request_client(user=staff_user).post(reverse("core:accounts"), data, **headers)
    account.refresh_from_db()
    computer_record.refresh_from_db()

    assert response.status_code == (302 if confirm and not ajax else 200)
    assert account.apply is confirm
    assert account.collect is confirm
    assert bool(computer_record.current_config_id) is confirm

    if not confirm:
        assert "Add allowed times to the schedule or explicitly confirm blocking all sessions." in response.content.decode()
        assert "type=\"checkbox\" name=\"account-confirm_empty_schedule\"" in response.content.decode()


def test_person_assignment_and_activation_validate_the_new_template(
    request_client: Callable[..., Client],
    user_create: Callable[..., User],
    computer_record: Computer,
    person_record: Person,
    limits_template_record: LimitsTemplate,
    range_record: Range,
) -> None:
    account = computer_record.accounts.get()
    person_record.limits_tpl = limits_template_record
    person_record.save(update_fields=("limits_tpl", "updated"))
    staff_user = user_create(attributes={"is_staff": True})

    response = request_client(user=staff_user).post(
        reverse("core:accounts"),
        {
            "account": f"{account.pk}",
            "__submit": "account",
            "account-person": f"{person_record.pk}",
            "account-apply": "on",
        },
    )
    account.refresh_from_db()

    assert response.status_code == 302
    assert account.person == person_record
    assert account.limits_id == range_record.limits_id
    assert account.collect is True
    assert account.apply is True


def test_person_change_cannot_silently_replace_active_limits_with_empty_schedule(
    request_client: Callable[..., Client],
    user_create: Callable[..., User],
    computer_record: Computer,
    person_record: Person,
    limits_template_record: LimitsTemplate,
) -> None:
    account = computer_record.accounts.get()
    previous_limits = Limits.objects.create(name="Previous independent limits")
    account.limits = previous_limits
    account.apply = True
    account.collect = True
    account.save(update_fields=("limits", "apply", "collect", "updated"))
    person_record.limits_tpl = limits_template_record
    person_record.save(update_fields=("limits_tpl", "updated"))
    staff_user = user_create(attributes={"is_staff": True})

    response = request_client(user=staff_user).post(
        reverse("core:accounts"),
        {
            "account": f"{account.pk}",
            "__submit": "account",
            "account-person": f"{person_record.pk}",
            "account-apply": "on",
        },
        HTTP_HX_REQUEST="true",
        HTTP_HX_TRIGGER="account-save",
    )
    account.refresh_from_db()

    assert response.status_code == 200
    assert "explicitly confirm blocking all sessions" in response.content.decode()
    assert account.person_id is None
    assert account.limits == previous_limits


@pytest.mark.parametrize("confirmed", [False, True])
def test_accounts_distinguish_requested_and_confirmed_settings(
    request_client: Callable[..., Client],
    user_create: Callable[..., User],
    computer_record: Computer,
    range_record: Range,
    confirmed: bool,
) -> None:
    account = computer_record.accounts.get()
    account.limits = range_record.limits
    account.apply = True
    account.collect = True
    account.save(update_fields=("limits", "apply", "collect", "updated"))
    config = computer_record.materialize_config()

    if confirmed:
        computer_record.acknowledge_config(config.ident)

    staff_user = user_create(attributes={"is_staff": True})
    response = request_client(user=staff_user).get(reverse("core:accounts"))
    content = response.content.decode()

    assert response.status_code == 200
    assert ("Settings confirmed" in content) is confirmed
    assert ("Waiting for confirmation" in content) is not confirmed
    assert "not that every restriction succeeded" in content
    assert "sanex on this computer has not acknowledged the latest settings" in content


@pytest.mark.parametrize("template", [False, True])
def test_account_editor_explains_template_or_independent_scope(
    request_client: Callable[..., Client],
    user_create: Callable[..., User],
    computer_record: Computer,
    limits_record: Limits,
    template: bool,
) -> None:
    account = computer_record.accounts.get()
    account.limits = limits_record
    account.save(update_fields=("limits", "updated"))

    if template:
        LimitsTemplate.objects.create(name="Family template", current_limits=limits_record)

    staff_user = user_create(attributes={"is_staff": True})
    response = request_client(user=staff_user).get(
        reverse("core:accounts"),
        {"account": account.pk},
        HTTP_HX_REQUEST="true",
        HTTP_HX_TRIGGER=f"account-edit-{account.pk}",
    )
    content = response.content.decode()

    assert response.status_code == 200
    assert ("Template schedule" in content) is template
    assert ("Existing accounts keep their assigned version." in content) is template
    assert ("Changes affect only the account listed below." in content) is not template
    assert "Accounts using this version" in content


def test_shared_old_snapshot_requires_independent_customization(
    request_client: Callable[..., Client],
    user_create: Callable[..., User],
    computer_record: Computer,
    limits_record: Limits,
) -> None:
    account = computer_record.accounts.get()
    account.limits = limits_record
    account.save(update_fields=("limits", "updated"))
    Account.objects.create(computer=computer_record, limits=limits_record, uid=1002, login="second", name="Second child")
    staff_user = user_create(attributes={"is_staff": True})

    response = request_client(user=staff_user).get(reverse("core:accounts"), {"account": account.pk})
    content = response.content.decode()

    assert response.status_code == 200
    assert "This version is shared by several accounts." in content
    assert "Second child" in content
    assert "Customize separately" in content
    assert f"href=\"{reverse("core:session_rules", args=(limits_record.pk,))}\"" not in content
