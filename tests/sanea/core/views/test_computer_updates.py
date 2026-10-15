"""Tests for the dedicated client updates page."""

from collections.abc import Callable
from datetime import timedelta
from typing import Any

from django.test import Client
from django.urls import reverse
from django.utils import timezone
from time_machine import TimeMachineFixture

from sanea.core.models import ClientCommand, Computer, GlobalUpdate, User


def test_computers_activate_replace_and_cancel_global_update(
    request_client: Callable[..., Client],
    user_create: Callable[..., User],
    computer_record: Computer,
    updates_payload: dict[str, Any],
    time_machine: TimeMachineFixture,
) -> None:
    staff_user = user_create(attributes={"is_staff": True})
    Computer.objects.create(hostname="blocked-pc", status="blocked")
    client = request_client(user=staff_user)
    form_data = {
        "__submit": "update",
        **updates_payload["valid"],
    }

    response = client.post(
        reverse("core:computer_updates"),
        form_data,
        HTTP_HX_REQUEST="true",
        HTTP_HX_TRIGGER="update-save",
    )
    replacement_data = {
        **form_data,
        "version": "0.3.1",
    }
    time_machine.shift(1)
    replaced = client.post(
        reverse("core:computer_updates"),
        replacement_data,
        HTTP_HX_REQUEST="true",
        HTTP_HX_TRIGGER="update-save",
    )
    commands = list(ClientCommand.objects.all())
    content = response.content.decode()
    replaced_content = replaced.content.decode()
    updates = list(GlobalUpdate.objects.order_by("created", "pk"))

    assert response.status_code == 200
    assert len(commands) == 1
    assert commands[0].computer == computer_record
    assert commands[0].type == "update"
    assert commands[0].payload == {
        **updates_payload["valid"],
        "version": "0.3.1",
    }
    assert commands[0].status is None
    assert "Update queued for 1 computer." in content
    assert replaced.status_code == 200
    assert ClientCommand.objects.count() == 1
    assert len(updates) == 2
    assert updates[0].active is False
    assert updates[0].cancelled == timezone.now()
    assert updates[1].created == updates[0].created + timedelta(seconds=1)
    assert updates[1].active is True
    assert "Active update: sanex 0.3.1" in replaced_content

    time_machine.shift(1)
    cancelled = client.post(
        reverse("core:computer_updates"),
        {"__submit": "update_cancel"},
        HTTP_HX_REQUEST="true",
        HTTP_HX_TRIGGER="update-cancel",
    )

    assert cancelled.status_code == 200
    assert "The update was cancelled." in cancelled.content.decode()
    assert GlobalUpdate.get_active() is None
    assert ClientCommand.objects.count() == 0



def test_computers_reject_invalid_global_update(
    request_client: Callable[..., Client],
    user_create: Callable[..., User],
    computer_record: Computer,
    updates_payload: dict[str, Any],
) -> None:
    staff_user = user_create(attributes={"is_staff": True})

    response = request_client(user=staff_user).post(
        reverse("core:computer_updates"),
        {"__submit": "update", **updates_payload["invalid"]},
        HTTP_HX_REQUEST="true",
        HTTP_HX_TRIGGER="update-save",
    )
    content = response.content.decode()

    assert response.status_code == 200
    assert "version conforming to PEP 440" in content
    assert "absolute HTTPS URL" in content
    assert ClientCommand.objects.count() == 0
