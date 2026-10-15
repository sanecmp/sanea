"""Tests for people management."""

from urllib.parse import urlencode
from typing import Any
from collections.abc import Callable

import pytest
from django.urls import reverse
from django.test import Client

from sanea.core.models import LimitsTemplate, Person, Computer, User


def test_people_requires_management_user(request_client: Callable[..., Client], user_create: Callable[..., User]) -> None:
    anonymous_response = request_client().get(reverse("core:people"))
    regular_response = request_client(user=user_create()).get(reverse("core:people"))

    assert anonymous_response.status_code == 302
    assert anonymous_response.url.startswith(reverse("core:sign_in"))
    assert regular_response.status_code == 403


def test_people_lists_domain_records(
    request_client: Callable[..., Client],
    user_create: Callable[..., User],
    person_record: Person,
) -> None:
    staff_user = user_create(attributes={"is_staff": True})

    response = request_client(user=staff_user).get(reverse("core:people"))
    content = response.content.decode()

    assert response.status_code == 200
    assert person_record.name in content
    assert "Local accounts" in content
    assert "<td class=\"small text-body-secondary text-center\">0</td>" in content
    assert "Limits template" in content
    assert "id=\"person-add\"" in content
    add_button = content.split("id=\"person-add\"", 1)[1].split("</a>", 1)[0]
    assert add_button.index("<use href=\"#icon-plus\">") < add_button.index("Add person")
    assert f"hx-get=\"{reverse("core:people") + "?" + urlencode({"person": "new"})}\"" in content
    assert "id=\"person-dialog\"" in content
    assert "sanea/js/editor-dialog.js" in content
    assert "sanea/css/people.css" in content
    assert "person-propagate-" not in content
    assert f"aria-label=\"Edit: {person_record.name}\"" in content
    assert "<use href=\"#icon-edit\">" in content


def test_people_links_child_to_the_combined_limits_card(
    request_client: Callable[..., Client],
    user_create: Callable[..., User],
    person_record: Person,
    computer_record: Computer,
) -> None:
    account = computer_record.accounts.get()
    account.person = person_record
    account.save(update_fields=("person", "updated"))
    staff_user = user_create(attributes={"is_staff": True})

    response = request_client(user=staff_user).get(reverse("core:people"))

    assert response.status_code == 200
    assert f"href=\"{reverse("core:account_limits", args=(account.pk,))}\"" in response.content.decode()
    assert "<td class=\"small text-body-secondary text-center\">1</td>" in response.content.decode()


def test_people_uses_short_local_accounts_heading_in_russian(
    request_client: Callable[..., Client], user_create: Callable[..., User],
) -> None:
    client = request_client(user=user_create(attributes={"is_staff": True}))

    response = client.get(reverse("core:people"), HTTP_ACCEPT_LANGUAGE="ru")

    assert response.status_code == 200
    assert '<th scope="col">Локальные учётки</th>' in response.content.decode()


def test_people_ajax_create_and_update(
    request_client: Callable[..., Client],
    user_create: Callable[..., User],
    person_record: Person,
    people_payload: dict[str, Any],
) -> None:
    staff_user = user_create(attributes={"is_staff": True})
    client = request_client(user=staff_user)
    ajax_headers = {
        "HTTP_HX_REQUEST": "true",
        "HTTP_HX_TRIGGER": "person-save",
    }

    editor_response = client.get(
        reverse("core:people"), {"person": "new"},
        HTTP_HX_REQUEST="true",
        HTTP_HX_TRIGGER="person-add",
    )
    assert editor_response.status_code == 200
    assert "name=\"person-name\"" in editor_response.content.decode()

    create_response = client.post(
        reverse("core:people"),
        {
            "__submit": "person",
            "person": "new",
            "person-name": people_payload["created"]["name"],
        },
        **ajax_headers,
    )
    create_content = create_response.content.decode()

    assert create_response.status_code == 200
    assert people_payload["created"]["name"] in create_content
    assert "hx-swap-oob=\"outerHTML\"" in create_content
    assert Person.objects.filter(name=people_payload["created"]["name"]).exists()

    update_response = client.post(
        reverse("core:people"),
        {
            "__submit": "person",
            "person": f"{person_record.pk}",
            "person-name": people_payload["renamed"]["name"],
        },
        **ajax_headers,
    )
    person_record.refresh_from_db()

    assert update_response.status_code == 200
    assert person_record.name == people_payload["renamed"]["name"]

def test_people_name_changes_preserve_template_and_account_limits(
    request_client: Callable[..., Client],
    user_create: Callable[..., User],
    person_record: Person,
    limits_template_record: LimitsTemplate,
    computer_record: Computer,
) -> None:
    staff_user = user_create(attributes={"is_staff": True})
    account = computer_record.accounts.get()
    account.person = person_record
    account.save(update_fields=("person", "updated"))
    previous_limits_id = account.limits_id
    person_record.limits_tpl = limits_template_record
    person_record.save(update_fields=("limits_tpl", "updated"))

    response = request_client(user=staff_user).post(
        reverse("core:people"),
        {
            "__submit": "person",
            "person": f"{person_record.pk}",
            "person-name": person_record.name,
            "person-limits_tpl": "",
        },
        HTTP_HX_REQUEST="true",
        HTTP_HX_TRIGGER="person-save",
    )
    person_record.refresh_from_db()
    account.refresh_from_db()

    assert response.status_code == 200
    assert person_record.limits_tpl == limits_template_record
    assert account.limits_id == previous_limits_id


@pytest.mark.parametrize("partial", [False, True], ids=["ordinary", "ajax"])
def test_people_editor_keeps_invalid_values_and_cancel_does_not_save(
    request_client: Callable[..., Client],
    user_create: Callable[..., User],
    person_record: Person,
    partial: bool,
) -> None:
    client = request_client(user=user_create(attributes={"is_staff": True}))
    ajax_headers = {"HTTP_HX_REQUEST": "true", "HTTP_HX_TRIGGER": "person-save"} if partial else {}
    previous_name = person_record.name

    response = client.post(
        reverse("core:people"),
        {"__submit": "person", "person": person_record.pk, "person-name": ""},
        **ajax_headers,
    )
    content = response.content.decode()

    assert response.status_code == 200
    assert "id=\"person-save\"" in content
    assert "This field is required." in content
    assert "id=\"person-dialog-title\"" in content
    assert "person-limits_tpl" not in content
    assert "prepare_template" not in content

    cancel_headers = {"HTTP_HX_REQUEST": "true", "HTTP_HX_TRIGGER": "person-cancel"} if partial else {}
    cancelled = client.get(reverse("core:people"), **cancel_headers)
    person_record.refresh_from_db()

    assert cancelled.status_code == 200
    assert "id=\"person-save\"" not in cancelled.content.decode()
    assert person_record.name == previous_name


def test_people_can_add_person_without_javascript(
    request_client: Callable[..., Client],
    user_create: Callable[..., User],
) -> None:
    client = request_client(user=user_create(attributes={"is_staff": True}))

    editor = client.get(reverse("core:people"), {"person": "new"})

    assert editor.status_code == 200
    assert "id=\"person-save\"" in editor.content.decode()
    assert "name=\"prepare_template\"" not in editor.content.decode()

    response = client.post(
        reverse("core:people"),
        {"__submit": "person", "person": "new", "person-name": "Synthetic person"},
    )

    assert response.status_code == 302
    assert response.url == reverse("core:people")
    assert Person.objects.filter(name="Synthetic person").exists()
