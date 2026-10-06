"""Tests for limits set management."""

from typing import Any
from collections.abc import Callable

from django.urls import reverse
from django.test import Client

from sanea.core.models import LimitsTemplate, User


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
    assert "id=\"limits-add\"" in content
    assert f"id=\"limits-edit-{limits_template_record.pk}\"" in content


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
