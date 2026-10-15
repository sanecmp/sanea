"""Tests for the dedicated command history page."""

from collections.abc import Callable
from typing import Any
from urllib.parse import parse_qs, urlsplit

from django.test import Client
from django.urls import reverse
from django.utils import timezone
from django.utils.formats import date_format

from sanea.core.models import ClientCommand, Computer, User


def test_command_history_refreshes_results_without_filters_or_computer_overview(
    request_client: Callable[..., Client], user_create: Callable[..., User], computer_record: Computer,
) -> None:
    command = ClientCommand.objects.create(computer=computer_record, type="diagnostic", payload={})

    response = request_client(user=user_create(attributes={"is_staff": True})).get(
        reverse("core:computer_commands"), {"command_computer": computer_record.pk, "command_status": "pending"},
        HTTP_HX_REQUEST="true", HTTP_HX_TRIGGER="command-live-refresh",
    )
    content = response.content.decode()

    assert response.status_code == 200
    assert "id=\"command-history-results\"" in content
    assert f"id=\"command-{command.pk}\"" in content
    summary = content.split("<summary class=\"sanea-command-summary\">", 1)[1].split("</summary>", 1)[0]
    assert "fw-semibold" not in summary
    assert date_format(timezone.localtime(command.created), "Y-m-d H:i") in content
    assert "id=\"command-filter\"" not in content
    assert "id=\"computer-table\"" not in content
    assert "sanea-shell" not in content


def test_failed_command_repeat_without_javascript_preserves_filters_and_page(
    request_client: Callable[..., Client], user_create: Callable[..., User], computer_record: Computer,
) -> None:
    command = ClientCommand.objects.create(
        computer=computer_record, type="diagnostic", payload={}, status="failed", completed=timezone.now(),
    )
    filters = {
        "command_computer": f"{computer_record.pk}", "command_type": "diagnostic",
        "command_status": "failed", "command_page": "2",
    }

    response = request_client(user=user_create(attributes={"is_staff": True})).post(
        reverse("core:computer_commands"), {"__submit": "command_repeat", "command": command.pk, **filters},
    )

    assert response.status_code == 302
    assert urlsplit(response.url).path == reverse("core:computer_commands")
    assert parse_qs(urlsplit(response.url).query) == {key: [value] for key, value in filters.items()}
    assert ClientCommand.objects.filter(computer=computer_record, type="diagnostic", status__isnull=True).count() == 1


def test_computers_filter_all_command_types_by_status(
    request_client: Callable[..., Client],
    user_create: Callable[..., User],
    computer_record: Computer,
    updates_payload: dict[str, Any],
) -> None:
    staff_user = user_create(attributes={"is_staff": True})
    completed = timezone.now()
    other_computer = Computer.objects.create(hostname="other-command-computer")
    ClientCommand.objects.create(
        computer=computer_record,
        type="update",
        payload=updates_payload["valid"],
        status="done",
        completed=completed,
    )
    diagnostic_command = ClientCommand.objects.create(
        computer=computer_record,
        type="diagnostic",
        payload={"scope": "network"},
        status="failed",
        error="Connection refused",
        completed=completed,
    )
    ClientCommand.objects.create(
        computer=computer_record,
        type="inventory",
        payload={"include": "accounts"},
    )
    ClientCommand.objects.create(
        computer=other_computer,
        type="diagnostic",
        payload={"scope": "storage"},
        status="failed",
        error="Disk unavailable",
        completed=completed,
    )

    response = request_client(user=staff_user).get(
        reverse("core:computer_commands"),
        {
            "command_computer": computer_record.pk,
            "command_type": "diagnostic",
            "command_status": "failed",
        },
        HTTP_HX_REQUEST="true",
        HTTP_HX_TRIGGER="command-filter",
    )
    content = response.content.decode()

    assert response.status_code == 200
    assert "id=\"command-history\"" in content
    assert "name=\"command_computer\"" in content
    assert "name=\"command_type\"" in content
    assert "name=\"command_status\"" in content
    assert "Command:</label>" in content
    assert "Type:</label>" not in content
    assert (
        f"<details class=\"list-group-item px-4 py-3\" id=\"command-{diagnostic_command.pk}\">"
        in content
    )
    assert "Command ID" in content
    assert "Last updated" in content
    assert "Payload" in content
    assert "diagnostic" in content
    assert "network" in content
    assert "Connection refused" in content
    assert "storage" not in content
    assert "Disk unavailable" not in content
    assert updates_payload["valid"]["version"] not in content
    assert "sanea-shell" not in content



def test_computers_repeat_failed_command_once(
    request_client: Callable[..., Client],
    user_create: Callable[..., User],
    computer_record: Computer,
) -> None:
    staff_user = user_create(attributes={"is_staff": True})
    source = ClientCommand.objects.create(
        computer=computer_record,
        type="diagnostic",
        payload={"scope": "network", "options": {"verbose": True}},
        status="failed",
        error="Connection refused",
        completed=timezone.now(),
    )
    client = request_client(user=staff_user)
    form_data = {
        "__submit": "command_repeat",
        "command": source.pk,
        "command_computer": computer_record.pk,
        "command_type": "diagnostic",
        "command_status": "failed",
    }
    request_options = {
        "HTTP_HX_REQUEST": "true",
        "HTTP_HX_TRIGGER": f"command-repeat-{source.pk}",
    }

    response = client.post(reverse("core:computer_commands"), form_data, **request_options)
    repeated_response = client.post(reverse("core:computer_commands"), form_data, **request_options)
    commands = list(ClientCommand.objects.order_by("pk"))
    content = response.content.decode()
    repeated_content = repeated_response.content.decode()

    assert response.status_code == 200
    assert len(commands) == 2
    assert commands[0] == source
    assert commands[0].status == "failed"
    assert commands[0].error == "Connection refused"
    assert commands[1].computer == source.computer
    assert commands[1].type == source.type
    assert commands[1].payload == source.payload
    assert commands[1].status is None
    assert "Command queued again." in content
    assert f"id=\"command-repeat-{source.pk}\"" in content
    assert repeated_response.status_code == 200
    assert "An identical command is already pending." in repeated_content



def test_computers_paginate_command_history_with_filters(
    request_client: Callable[..., Client],
    user_create: Callable[..., User],
    computer_record: Computer,
) -> None:
    staff_user = user_create(attributes={"is_staff": True})
    commands = ClientCommand.objects.bulk_create(
        [
            ClientCommand(
                computer=computer_record,
                type="diagnostic",
                payload={"position": position},
                status="failed",
                error=f"Failure {position}",
                completed=timezone.now(),
            )
            for position in range(101)
        ]
    )
    client = request_client(user=staff_user)
    filters = {
        "access": "allowed",
        "command_computer": computer_record.pk,
        "command_type": "diagnostic",
        "command_status": "failed",
    }

    first_response = client.get(
        reverse("core:computer_commands"),
        filters,
        HTTP_HX_REQUEST="true",
        HTTP_HX_TRIGGER="command-filter",
    )
    first_content = first_response.content.decode()
    second_response = client.get(
        reverse("core:computer_commands"),
        {**filters, "command_page": 2},
        HTTP_HX_REQUEST="true",
        HTTP_HX_TRIGGER="command-page-next",
    )
    second_content = second_response.content.decode()

    assert first_response.status_code == 200
    assert first_content.count("<details class=\"list-group-item px-4 py-3\"") == 100
    assert f"id=\"command-{commands[-1].pk}\"" in first_content
    assert f"id=\"command-{commands[0].pk}\"" not in first_content
    assert "id=\"command-page-next\"" in first_content
    assert f"command_computer={computer_record.pk}" in first_content
    assert "command_type=diagnostic" in first_content
    assert "command_status=failed" in first_content
    assert "command_page=2" in first_content
    assert second_response.status_code == 200
    assert second_content.count("<details class=\"list-group-item px-4 py-3\"") == 1
    assert f"id=\"command-{commands[0].pk}\"" in second_content
    assert f"id=\"command-{commands[-1].pk}\"" not in second_content
    assert (
        "id=\"command-current-page\" type=\"hidden\" name=\"command_page\" value=\"2\""
        in second_content
    )
    assert "id=\"command-page-previous\"" in second_content
    assert "id=\"command-page-next\"" not in second_content



def test_computers_open_commands_for_selected_computer(
    request_client: Callable[..., Client],
    user_create: Callable[..., User],
    computer_record: Computer,
) -> None:
    staff_user = user_create(attributes={"is_staff": True})
    other_computer = Computer.objects.create(hostname="other-pc")
    selected_command = ClientCommand.objects.create(
        computer=computer_record,
        type="diagnostic",
        payload={"scope": "selected-command-payload"},
    )
    ClientCommand.objects.create(
        computer=other_computer,
        type="diagnostic",
        payload={"scope": "other-command-payload"},
    )

    response = request_client(user=staff_user).get(
        reverse("core:computer_commands"),
        {"command_computer": computer_record.pk},
        HTTP_HX_REQUEST="true",
        HTTP_HX_TRIGGER="command-filter",
    )
    content = response.content.decode()

    assert response.status_code == 200
    assert "id=\"command-history\"" in content
    assert f"<option value=\"{computer_record.pk}\" selected>" in content
    assert f"id=\"command-{selected_command.pk}\"" in content
    assert "selected-command-payload" in content
    assert "other-command-payload" not in content
    assert "sanea-shell" not in content



def test_computers_open_filtered_commands_from_counts(
    request_client: Callable[..., Client],
    user_create: Callable[..., User],
    computer_record: Computer,
) -> None:
    staff_user = user_create(attributes={"is_staff": True})
    pending_command = ClientCommand.objects.create(
        computer=computer_record,
        type="diagnostic",
        payload={"scope": "pending-command-payload"},
    )
    failed_command = ClientCommand.objects.create(
        computer=computer_record,
        type="diagnostic",
        payload={"scope": "failed-command-payload"},
        status="failed",
        error="Diagnostic failed",
        completed=timezone.now(),
    )
    client = request_client(user=staff_user)

    list_response = client.get(reverse("core:computers"))
    response = client.get(
        reverse("core:computer_commands"),
        {
            "command_computer": computer_record.pk,
            "command_status": "pending",
        },
        HTTP_HX_REQUEST="true",
        HTTP_HX_TRIGGER="command-filter",
    )
    content = response.content.decode()
    list_content = list_response.content.decode()

    assert list_response.status_code == 200
    assert f"id=\"computer-command-pending-{computer_record.pk}\"" in list_content
    assert f"id=\"computer-command-failed-{computer_record.pk}\"" in list_content
    assert "title=\"Pending\"" in list_content
    assert "title=\"Failed\"" in list_content
    assert response.status_code == 200
    assert "id=\"command-history\"" in content
    assert f"<option value=\"{computer_record.pk}\" selected>" in content
    assert "<option value=\"pending\" selected>Pending</option>" in content
    assert f"id=\"command-{pending_command.pk}\"" in content
    assert "pending-command-payload" in content
    assert "failed-command-payload" not in content
    assert "sanea-shell" not in content

    failed_response = client.get(
        reverse("core:computer_commands"),
        {
            "command_computer": computer_record.pk,
            "command_status": "failed",
        },
        HTTP_HX_REQUEST="true",
        HTTP_HX_TRIGGER="command-filter",
    )
    failed_content = failed_response.content.decode()

    assert failed_response.status_code == 200
    assert "<option value=\"failed\" selected>Failed</option>" in failed_content
    assert f"id=\"command-{failed_command.pk}\"" in failed_content
    assert "failed-command-payload" in failed_content
    assert "pending-command-payload" not in failed_content
    assert "sanea-shell" not in failed_content
