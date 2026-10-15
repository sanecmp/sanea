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


@pytest.mark.parametrize("present, collect", [(False, True), (True, False)])
def test_accounts_lists_reported_records(
    request_client: Callable[..., Client],
    user_create: Callable[..., User],
    computer_record: Computer,
    present: bool,
    collect: bool,
) -> None:
    staff_user = user_create(attributes={"is_staff": True})
    account = Account.objects.get(computer=computer_record)
    account.present = present
    account.collect = collect
    account.save(update_fields=("present", "collect", "updated"))

    response = request_client(user=staff_user).get(reverse("core:accounts"))
    content = response.content.decode()

    assert response.status_code == 200
    assert account.login in content
    assert computer_record.name in content
    assert f"id=\"account-edit-{account.pk}\"" in content
    assert "sanea-mobile-table" in content
    assert "sanea-table-actions" in content
    assert '<td class="small text-body-secondary" data-label="Computer">' in content
    assert '<td class="small text-body-secondary" data-label="Person">—</td>' in content
    assert '<ul class="text-body-secondary small mt-2 mb-0 ps-3">' not in content
    assert "<details" not in content
    assert '<th scope="col" class="text-center">Monitoring</th>' in content
    assert '<td class="text-center" data-label="Monitoring">' in content
    monitoring_markup = content.split('data-label="Monitoring">', 1)[1].split("</td>", 1)[0]
    monitoring = "Enabled" if collect else "Disabled"
    monitoring_icon = "check" if collect else "ban"
    assert f'title="Monitoring: {monitoring}"' in monitoring_markup
    assert f'aria-label="Monitoring: {monitoring}"' in monitoring_markup
    assert 'class="sanea-status-icon" role="img"' in monitoring_markup
    assert f'<use href="#icon-{monitoring_icon}">' in monitoring_markup
    assert "badge" not in monitoring_markup
    assert "data-label=\"On computer\"" in content
    presence = "Exists" if present else "Missing"
    icon = "check" if present else "ban"
    assert presence in content
    assert "not an active session" in content
    assert "Add account" not in content
    assert "id=\"account-dialog\"" in content
    assert "data-dialog-editor" in content
    assert "id=\"account-save\"" not in content
    assert f"aria-label=\"Configure: {account.login} · {computer_record.get_display_name()}\"" in content
    assert "<use href=\"#icon-edit\">" in content
    assert "<use href=\"#icon-limits\">" in content
    assert "<td class=\"text-center\" data-label=\"On computer\">" in content
    assert f"role=\"img\" aria-label=\"{presence}\"" in content
    assert f"<use href=\"#icon-{icon}\">" in content


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
    editor_content = editor_response.content.decode()

    assert editor_response.status_code == 200
    assert editor_content.index('name="account-collect"') < editor_content.index('name="account-apply"')
    assert editor_content.index('name="account-apply"') < editor_content.index('name="account-person"')

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
    assert f'data-label="Person">{person_record.name}</td>' in save_response.content.decode()
    assert "hx-swap-oob=\"outerHTML\"" in save_response.content.decode()
    assert "id=\"accounts-message\"" in save_response.content.decode()
    assert "id=\"account-save\"" not in save_response.content.decode()


@pytest.mark.parametrize("ajax", [False, True])
def test_account_editor_cancels_without_saving_and_preserves_invalid_input(
    request_client: Callable[..., Client],
    user_create: Callable[..., User],
    computer_record: Computer,
    ajax: bool,
) -> None:
    client = request_client(user=user_create(attributes={"is_staff": True}))
    account = Account.objects.get(computer=computer_record)
    original_collect = account.collect
    headers = {"HTTP_HX_REQUEST": "true", "HTTP_HX_TRIGGER": "account-save"} if ajax else {}

    response = client.post(
        reverse("core:accounts"),
        {"account": f"{account.pk}", "__submit": "account", "account-person": "not-a-person"},
        **headers,
    )

    assert response.status_code == 200
    assert "id=\"account-dialog-title\"" in response.content.decode()
    assert "data-dialog-panel" in response.content.decode()
    assert "Select a valid choice." in response.content.decode()

    cancel_headers = {"HTTP_HX_REQUEST": "true", "HTTP_HX_TRIGGER": "account-cancel"} if ajax else {}
    cancelled = client.get(reverse("core:accounts"), **cancel_headers)
    account.refresh_from_db()

    assert cancelled.status_code == 200
    assert "id=\"account-save\"" not in cancelled.content.decode()
    assert account.person_id is None
    assert account.collect is original_collect
    assert account.limits_id is None



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


@pytest.mark.parametrize(
    "configured, applied, confirmed, label, icon",
    [
        pytest.param(True, True, True, "Settings confirmed", "check", id="confirmed"),
        pytest.param(True, True, False, "Waiting for confirmation", "clock", id="waiting"),
        pytest.param(True, False, True, "Not applied", "ban", id="disabled"),
        pytest.param(False, False, True, "Not configured", "minus", id="not-configured"),
    ],
)
def test_accounts_distinguish_limit_states_with_accessible_icons(
    request_client: Callable[..., Client],
    user_create: Callable[..., User],
    computer_record: Computer,
    range_record: Range,
    configured: bool,
    applied: bool,
    confirmed: bool,
    label: str,
    icon: str,
) -> None:
    account = computer_record.accounts.get()
    account.limits = range_record.limits if configured else None
    account.apply = applied
    account.collect = True
    account.save(update_fields=("limits", "apply", "collect", "updated"))
    config = computer_record.materialize_config()

    if confirmed:
        computer_record.acknowledge_config(config.ident)

    staff_user = user_create(attributes={"is_staff": True})
    response = request_client(user=staff_user).get(reverse("core:accounts"))
    content = response.content.decode()

    assert response.status_code == 200
    assert '<th scope="col" class="text-center">Limits</th>' in content
    assert '<td class="text-center" data-label="Limits">' in content
    limits_markup = content.split('data-label="Limits">', 1)[1].split("</td>", 1)[0]
    assert f'title="Limits: {label}' in limits_markup
    assert f'aria-label="Limits: {label}"' in limits_markup
    assert 'class="sanea-status-icon" role="img"' in limits_markup
    assert f'<use href="#icon-{icon}">' in limits_markup
    assert f'<symbol id="icon-{icon}" viewBox="0 0 24 24">' in content
    assert "badge" not in limits_markup
    assert ("not that every restriction succeeded" in limits_markup) is (applied and confirmed)
    assert ("sanex on this computer has not acknowledged the latest settings" in limits_markup) is (applied and not confirmed)


@pytest.mark.parametrize("template", [False, True])
def test_account_editor_keeps_limit_management_on_the_limits_page(
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
    assert "id=\"account-dialog-title\"" in content
    assert "data-dialog-panel" in content
    assert "data-dialog-close" in content
    assert "name=\"account-person\"" in content
    assert "name=\"account-collect\"" in content
    assert "name=\"account-apply\"" in content
    assert "Schedule, sessions and applications" not in content
    assert "Existing accounts are updated separately." not in content
    assert "Changes affect only the account listed below." not in content
    assert "Accounts using this version" not in content
    assert "Customize separately" not in content
    assert "Limits:" not in content
    account.refresh_from_db()
    assert account.limits_id == limits_record.pk


def test_account_editor_without_javascript_keeps_shared_limits_unchanged(
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
    assert "id=\"account-save\"" in content
    assert "data-dialog-panel" in content
    assert "This version is shared by several accounts." not in content
    assert "Customize separately" not in content
    assert f"href=\"{reverse("core:session_rules", args=(limits_record.pk,))}\"" not in content
    account.refresh_from_db()
    assert account.limits_id == limits_record.pk
