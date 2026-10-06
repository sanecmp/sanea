"""Tests for the registered computers interface."""

from datetime import timedelta
from urllib.parse import urlencode
from importlib import import_module
from collections.abc import Callable
from typing import Any

from django.urls import reverse
from time_machine import TimeMachineFixture
from django.utils.html import escape
import pytest
from django.utils import timezone
from django.test import Client

from sanea.core.models import ClientCommand, Computer, GlobalUpdate, User
from sanea.core.services.registration_window import RegistrationWindow


@pytest.fixture
def registration_window_state(monkeypatch: pytest.MonkeyPatch) -> tuple[RegistrationWindow, list[float]]:
    """Install an isolated registration window with a controllable clock."""
    now = [100.0]
    window = RegistrationWindow(clock=lambda: now[0])
    computers_module = import_module("sanea.core.views.computers")
    monkeypatch.setattr(computers_module, "registration_window", window)
    return window, now


def test_computers_requires_management_user(
    request_client: Callable[..., Client],
    user_create: Callable[..., User],
    registration_window_state: tuple[RegistrationWindow, list[float]],
) -> None:
    window, _ = registration_window_state
    anonymous_response = request_client().get(reverse("core:computers"))
    regular_client = request_client(user=user_create())
    regular_response = regular_client.get(reverse("core:computers"))
    regular_open_response = regular_client.post(
        reverse("core:computers"),
        HTTP_HX_REQUEST="true",
        HTTP_HX_TRIGGER="registration-open",
    )

    assert anonymous_response.status_code == 302
    assert anonymous_response.url.startswith(reverse("core:sign_in"))
    assert regular_response.status_code == 403
    assert regular_open_response.status_code == 403
    assert window.get_snapshot() is None


def test_computers_lists_registered_clients(
    request_client: Callable[..., Client],
    user_create: Callable[..., User],
    computer_record: Computer,
) -> None:
    staff_user = user_create(attributes={"is_staff": True})
    computer_record.last_seen = timezone.now()
    computer_record.save(update_fields=("last_seen", "updated"))
    ClientCommand.objects.create(
        computer=computer_record,
        type="diagnostic",
        payload={},
    )

    response = request_client(user=staff_user).get(reverse("core:computers"))
    content = response.content.decode()
    command_query = urlencode({"command_computer": computer_record.pk})
    issues_query = escape(urlencode({"computer": computer_record.pk, "period": "7-days"}))

    assert response.status_code == 200
    assert computer_record.name in content
    assert computer_record.hostname in content
    assert computer_record.version in content
    assert "Allowed" in content
    assert "Online" in content
    assert "Commands" in content
    assert "<span class=\"badge text-bg-warning\">1</span>" in content
    assert f"id=\"computer-command-pending-{computer_record.pk}\"" in content
    assert (
        f"command_computer={computer_record.pk}&amp;command_status=pending" in content
    )
    assert "collecting: 1" in content
    assert f"id=\"computer-actions-{computer_record.pk}\"" in content
    assert "data-bs-toggle=\"dropdown\"" in content
    assert "data-bs-config='{\"popperConfig\":{\"strategy\":\"fixed\"}}'" in content
    assert f"id=\"computer-commands-{computer_record.pk}\"" in content
    assert (
        f"href=\"{reverse("core:computers")}?{command_query}#command-history\""
        in content
    )
    assert f"href=\"{reverse("core:issues")}?{issues_query}\"" in content
    assert "hx-swap=\"outerHTML show:top\"" in content
    assert "id=\"computer-details-" in content
    assert "id=\"computer-filter\" class=\"sanea-computer-filter\"" in content
    assert "id=\"command-filter\" class=\"sanea-command-filter\"" in content
    assert "id=\"computer-live-refresh\"" in content
    assert "hx-trigger=\"every 10s\"" in content
    assert (
        "hx-include=\"#command-filter, #computer-filter, #command-current-page\""
        in content
    )
    assert "hx-swap=\"none\"" in content
    assert "Add computer" not in content


def test_computer_details_are_loaded_through_siteajax(
    request_client: Callable[..., Client],
    user_create: Callable[..., User],
    computer_record: Computer,
) -> None:
    staff_user = user_create(attributes={"is_staff": True})

    response = request_client(user=staff_user).get(
        reverse("core:computers"), {"computer": computer_record.pk},
        HTTP_HX_REQUEST="true",
        HTTP_HX_TRIGGER=f"computer-details-{computer_record.pk}",
    )
    content = response.content.decode()

    assert response.status_code == 200
    assert f"{computer_record.last_ip}" in content
    assert computer_record.timezone in content
    assert computer_record.certificate_fingerprint in content
    assert "300 seconds" in content
    assert f"id=\"computer-configure-{computer_record.pk}\"" in content


def test_staff_user_opens_registration_with_visible_countdown(
    request_client: Callable[..., Client],
    user_create: Callable[..., User],
    registration_window_state: tuple[RegistrationWindow, list[float]],
) -> None:
    window, now = registration_window_state
    staff_user = user_create(attributes={"is_staff": True})
    client = request_client(user=staff_user)

    response = client.post(
        reverse("core:computers"),
        HTTP_HX_REQUEST="true",
        HTTP_HX_TRIGGER="registration-open",
    )
    content = response.content.decode()
    code = window.get_snapshot().code

    assert response.status_code == 200
    assert "Registration is open" in content
    assert code in content
    assert f"sudo sanex register {code}" in content
    assert "data-registration-countdown=\"30000\"" in content
    assert "00:30" in content
    assert "registration-window.js" not in content

    now[0] = 130.0
    expired_response = client.get(
        reverse("core:computers"),
        HTTP_HX_REQUEST="true",
        HTTP_HX_TRIGGER="registration-refresh",
    )
    expired_content = expired_response.content.decode()

    assert expired_response.status_code == 200
    assert "Register a computer" in expired_content
    assert "Open registration for 30 seconds" in expired_content
    assert code not in expired_content


def test_computers_page_includes_registration_controls_and_countdown_script(
    request_client: Callable[..., Client],
    user_create: Callable[..., User],
    registration_window_state: tuple[RegistrationWindow, list[float]],
) -> None:
    staff_user = user_create(attributes={"is_staff": True})

    response = request_client(user=staff_user).get(reverse("core:computers"))
    content = response.content.decode()

    assert response.status_code == 200
    assert "Open registration for 30 seconds" in content
    assert "The exact sanex command with the current code will appear here" in content
    assert "src=\"/static/sanea/js/registration-window.js\"" in content


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
        reverse("core:computers"),
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
        reverse("core:computers"),
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
        reverse("core:computers"),
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
        reverse("core:computers"),
        {"__submit": "update", **updates_payload["invalid"]},
        HTTP_HX_REQUEST="true",
        HTTP_HX_TRIGGER="update-save",
    )
    content = response.content.decode()

    assert response.status_code == 200
    assert "version conforming to PEP 440" in content
    assert "absolute HTTPS URL" in content
    assert ClientCommand.objects.count() == 0


def test_computers_refresh_live_state_through_siteajax(
    request_client: Callable[..., Client],
    user_create: Callable[..., User],
    computer_record: Computer,
    updates_payload: dict[str, Any],
) -> None:
    staff_user = user_create(attributes={"is_staff": True})
    computer_record.last_seen = timezone.now()
    computer_record.save(update_fields=("last_seen", "updated"))
    command = ClientCommand.objects.create(
        computer=computer_record,
        type="update",
        payload=updates_payload["valid"],
        status="done",
    )

    response = request_client(user=staff_user).get(
        reverse("core:computers"),
        HTTP_HX_REQUEST="true",
        HTTP_HX_TRIGGER="computer-live-refresh",
    )
    content = response.content.decode()

    assert response.status_code == 200
    assert f"id=\"computer-connection-{computer_record.pk}\"" in content
    assert f"id=\"computer-last-contact-{computer_record.pk}\"" in content
    assert f"id=\"computer-command-counts-{computer_record.pk}\"" in content
    assert f"id=\"computer-config-status-{computer_record.pk}\"" in content
    assert "id=\"command-history-results\"" in content
    assert content.count("hx-swap-oob=\"outerHTML\"") == 5
    assert "Online" in content
    assert updates_payload["valid"]["version"] in content
    assert command.get_status_display() in content
    assert "sanea-shell" not in content


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
        reverse("core:computers"),
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


def test_computers_ajax_edits_access_and_runtime_intervals(
    request_client: Callable[..., Client],
    user_create: Callable[..., User],
    computer_record: Computer,
) -> None:
    staff_user = user_create(attributes={"is_staff": True})
    initial_config = computer_record.materialize_config()
    computer_record.applied_config = initial_config
    computer_record.save(update_fields=("applied_config", "updated"))
    client = request_client(user=staff_user)

    editor_response = client.get(
        reverse("core:computers"), {"computer": computer_record.pk, "edit": 1},
        HTTP_HX_REQUEST="true",
        HTTP_HX_TRIGGER=f"computer-configure-{computer_record.pk}",
    )
    editor_content = editor_response.content.decode()

    assert editor_response.status_code == 200
    assert "id=\"computer-save\"" in editor_content
    assert "name=\"computer-name\"" in editor_content
    assert "name=\"computer-status\"" in editor_content
    assert "name=\"computer-timezone\"" in editor_content
    assert "value=\"Asia/Novosibirsk\" selected" in editor_content
    assert "name=\"computer-sync_interval\"" in editor_content
    assert "name=\"computer-min_prc_duration\"" in editor_content

    save_response = client.post(
        reverse("core:computers"),
        {
            "__submit": "computer",
            "computer": f"{computer_record.pk}",
            "computer-name": "Bedroom computer",
            "computer-status": "blocked",
            "computer-timezone": "Europe/Berlin",
            "computer-sync_interval": "600",
            "computer-discovery_interval": "60",
            "computer-walk_interval": "2",
            "computer-save_interval": "10",
            "computer-min_prc_duration": "7",
        },
        HTTP_HX_REQUEST="true",
        HTTP_HX_TRIGGER="computer-save",
    )
    computer_record.refresh_from_db()
    content = save_response.content.decode()

    assert save_response.status_code == 200
    assert computer_record.name == "Bedroom computer"
    assert computer_record.status == "blocked"
    assert computer_record.timezone == "Europe/Berlin"
    assert computer_record.sync_interval == 600
    assert computer_record.discovery_interval == 60
    assert computer_record.walk_interval == 2
    assert computer_record.save_interval == 10
    assert computer_record.min_prc_duration == 7
    assert computer_record.current_config_id != initial_config.ident
    assert computer_record.applied_config_id == initial_config.ident
    assert "Computer settings saved." in content
    assert "id=\"computer-access-" in content
    assert "Blocked" in content
    assert "Waiting for sync" in content
    assert content.count("hx-swap-oob=\"outerHTML\"") == 3


def test_computers_reject_inconsistent_runtime_intervals(
    request_client: Callable[..., Client],
    user_create: Callable[..., User],
    computer_record: Computer,
) -> None:
    staff_user = user_create(attributes={"is_staff": True})

    response = request_client(user=staff_user).post(
        reverse("core:computers"),
        {
            "__submit": "computer",
            "computer": f"{computer_record.pk}",
            "computer-status": "allowed",
            "computer-timezone": "Asia/Novosibirsk",
            "computer-sync_interval": "20",
            "computer-discovery_interval": "30",
            "computer-walk_interval": "1",
            "computer-save_interval": "5",
            "computer-min_prc_duration": "5",
        },
        HTTP_HX_REQUEST="true",
        HTTP_HX_TRIGGER="computer-save",
    )
    computer_record.refresh_from_db()
    content = response.content.decode()

    assert response.status_code == 200
    assert "Must not exceed sync_interval." in content
    assert computer_record.sync_interval == 300
    assert computer_record.discovery_interval == 30
    assert "Computer settings saved." not in content


def test_computers_filter_access_connection_and_configuration(
    request_client: Callable[..., Client],
    user_create: Callable[..., User],
    computer_record: Computer,
) -> None:
    staff_user = user_create(attributes={"is_staff": True})
    computer_record.last_seen = timezone.now()
    computer_record.save(update_fields=("last_seen", "updated"))
    other = Computer.objects.create(
        hostname="blocked-offline-applied",
        status="blocked",
        last_seen=None,
    )
    applied_config = other.materialize_config()
    other.applied_config = applied_config
    other.save(update_fields=("applied_config", "updated"))

    response = request_client(user=staff_user).get(
        reverse("core:computers"),
        {
            "access": "blocked",
            "connection": "offline",
            "config_delivery": "applied",
        },
        HTTP_HX_REQUEST="true",
        HTTP_HX_TRIGGER="computer-filter",
    )
    content = response.content.decode()

    assert response.status_code == 200
    assert "id=\"computer-list\"" in content
    assert "id=\"computer-filter\"" in content
    assert other.hostname in content
    assert computer_record.hostname not in content
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

    response = client.post(reverse("core:computers"), form_data, **request_options)
    repeated_response = client.post(reverse("core:computers"), form_data, **request_options)
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
        reverse("core:computers"),
        filters,
        HTTP_HX_REQUEST="true",
        HTTP_HX_TRIGGER="command-filter",
    )
    first_content = first_response.content.decode()
    second_response = client.get(
        reverse("core:computers"),
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
    assert "access=allowed" in first_content
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
        reverse("core:computers"),
        {"command_computer": computer_record.pk},
        HTTP_HX_REQUEST="true",
        HTTP_HX_TRIGGER=f"computer-commands-{computer_record.pk}",
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
        reverse("core:computers"),
        {
            "command_computer": computer_record.pk,
            "command_status": "pending",
        },
        HTTP_HX_REQUEST="true",
        HTTP_HX_TRIGGER=f"computer-command-pending-{computer_record.pk}",
    )
    content = response.content.decode()
    list_content = list_response.content.decode()

    assert list_response.status_code == 200
    assert f"id=\"computer-command-pending-{computer_record.pk}\"" in list_content
    assert f"id=\"computer-command-failed-{computer_record.pk}\"" in list_content
    assert "<span class=\"badge text-bg-warning\">1</span>" in list_content
    assert "<span class=\"badge text-bg-danger\">1</span>" in list_content
    assert response.status_code == 200
    assert "id=\"command-history\"" in content
    assert f"<option value=\"{computer_record.pk}\" selected>" in content
    assert "<option value=\"pending\" selected>Pending</option>" in content
    assert f"id=\"command-{pending_command.pk}\"" in content
    assert "pending-command-payload" in content
    assert "failed-command-payload" not in content
    assert "sanea-shell" not in content

    failed_response = client.get(
        reverse("core:computers"),
        {
            "command_computer": computer_record.pk,
            "command_status": "failed",
        },
        HTTP_HX_REQUEST="true",
        HTTP_HX_TRIGGER=f"computer-command-failed-{computer_record.pk}",
    )
    failed_content = failed_response.content.decode()

    assert failed_response.status_code == 200
    assert "<option value=\"failed\" selected>Failed</option>" in failed_content
    assert f"id=\"command-{failed_command.pk}\"" in failed_content
    assert "failed-command-payload" in failed_content
    assert "pending-command-payload" not in failed_content
    assert "sanea-shell" not in failed_content
