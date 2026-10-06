"""Tests for people management."""

from urllib.parse import urlencode
from typing import Any
from collections.abc import Callable

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
    assert "Limits template" in content
    assert "id=\"person-add\"" in content
    assert f"hx-get=\"{reverse("core:people") + "?" + urlencode({"person": "new"})}\"" in content


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

def test_people_assigns_limits_template(
    request_client: Callable[..., Client],
    user_create: Callable[..., User],
    person_record: Person,
    limits_template_record: LimitsTemplate,
) -> None:
    staff_user = user_create(attributes={"is_staff": True})

    response = request_client(user=staff_user).post(
        reverse("core:people"),
        {
            "__submit": "person",
            "person": f"{person_record.pk}",
            "person-name": person_record.name,
            "person-limits_tpl": f"{limits_template_record.pk}",
        },
        HTTP_HX_REQUEST="true",
        HTTP_HX_TRIGGER="person-save",
    )
    person_record.refresh_from_db()

    assert response.status_code == 200
    assert person_record.limits_tpl == limits_template_record



def test_people_explicitly_distributes_current_template_snapshot(
    request_client: Callable[..., Client],
    user_create: Callable[..., User],
    computer_record: Computer,
    person_record: Person,
    limits_template_record: LimitsTemplate,
) -> None:
    staff_user = user_create(attributes={"is_staff": True})
    account = computer_record.accounts.get()
    person_record.limits_tpl = limits_template_record
    person_record.save(update_fields=("limits_tpl", "updated"))
    account.person = person_record
    account.save(update_fields=("person", "updated"))

    response = request_client(user=staff_user).post(
        reverse("core:people"),
        {
            "__submit": "propagation",
            "person": f"{person_record.pk}",
            "propagate_template": "1",
            "propagation-accounts": f"{account.pk}",
        },
        HTTP_HX_REQUEST="true",
        HTTP_HX_TRIGGER="person-propagate-save",
    )
    account.refresh_from_db()

    assert response.status_code == 200
    assert account.limits == limits_template_record.current_limits
    assert "hx-swap-oob=\"outerHTML\"" in response.content.decode()
