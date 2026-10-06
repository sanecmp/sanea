"""Tests for ignored process management."""

from typing import Any
from collections.abc import Callable

from django.urls import reverse
from django.test import Client

from sanea.core.models import PrcExclusion, User


def test_ignored_processes_requires_management_user(
    request_client: Callable[..., Client],
    user_create: Callable[..., User],
) -> None:
    anonymous_response = request_client().get(reverse("core:ignored_processes"))
    regular_response = request_client(user=user_create()).get(
        reverse("core:ignored_processes")
    )

    assert anonymous_response.status_code == 302
    assert anonymous_response.url.startswith(reverse("core:sign_in"))
    assert regular_response.status_code == 403


def test_ignored_processes_lists_names_and_add_form(
    request_client: Callable[..., Client],
    user_create: Callable[..., User],
    ignored_process_record: PrcExclusion,
) -> None:
    staff_user = user_create(attributes={"is_staff": True})
    client = request_client(user=staff_user)

    response = client.get(reverse("core:ignored_processes"))
    editor_response = client.get(
        reverse("core:ignored_processes"), {"exclusion": "new"},
        HTTP_HX_REQUEST="true",
        HTTP_HX_TRIGGER="ignored-process-add",
    )

    assert response.status_code == 200
    assert ignored_process_record.prc_name in response.content.decode()
    assert "id=\"ignored-process-add\"" in response.content.decode()
    assert editor_response.status_code == 200
    assert "name=\"exclusion-prc_name\"" in editor_response.content.decode()


def test_ignored_processes_ajax_adds_and_removes_names(
    request_client: Callable[..., Client],
    user_create: Callable[..., User],
    ignored_process_record: PrcExclusion,
    ignored_processes_payload: dict[str, Any],
) -> None:
    staff_user = user_create(attributes={"is_staff": True})
    client = request_client(user=staff_user)
    created_name = ignored_processes_payload["created"]["prc_name"]

    create_response = client.post(
        reverse("core:ignored_processes"),
        {
            "__submit": "exclusion",
            "exclusion-prc_name": created_name,
        },
        HTTP_HX_REQUEST="true",
        HTTP_HX_TRIGGER="ignored-process-save",
    )

    assert create_response.status_code == 200
    assert created_name in create_response.content.decode()
    assert "hx-swap-oob=\"outerHTML\"" in create_response.content.decode()
    assert PrcExclusion.objects.filter(prc_name=created_name).exists()

    delete_response = client.post(
        reverse("core:ignored_processes"),
        {
            "delete": "1",
            "exclusion": f"{ignored_process_record.pk}",
        },
        HTTP_HX_REQUEST="true",
        HTTP_HX_TRIGGER=f"ignored-process-delete-{ignored_process_record.pk}",
    )

    assert delete_response.status_code == 200
    ignored_process_record.refresh_from_db()
    assert ignored_process_record.apply is False

    restore_response = client.post(
        reverse("core:ignored_processes"),
        {
            "restore": "1",
            "exclusion": f"{ignored_process_record.pk}",
        },
        HTTP_HX_REQUEST="true",
        HTTP_HX_TRIGGER=f"ignored-process-restore-{ignored_process_record.pk}",
    )
    ignored_process_record.refresh_from_db()

    assert restore_response.status_code == 200
    assert ignored_process_record.apply is True
