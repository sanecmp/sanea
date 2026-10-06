"""Tests for local account management."""

from collections.abc import Callable

from django.urls import reverse
from django.test import Client

from sanea.core.models import Account, Person, Computer, LimitsTemplate, User


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
