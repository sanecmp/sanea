"""Tests for the registered computers interface."""

from urllib.parse import urlencode
from importlib import import_module
from collections.abc import Callable

from django.urls import reverse
from time_machine import TimeMachineFixture
import pytest
from django.utils import timezone
from django.utils.formats import date_format
from django.utils.html import escape
from django.test import Client

from sanea.core.models import ClientCommand, Computer, User
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
    request_client: Callable[..., Client], user_create: Callable[..., User], computer_record: Computer,
) -> None:
    computer_record.last_seen = timezone.now()
    computer_record.save(update_fields=("last_seen", "updated"))
    ClientCommand.objects.create(computer=computer_record, type="diagnostic", payload={})

    response = request_client(user=user_create(attributes={"is_staff": True})).get(reverse("core:computers"))
    content = response.content.decode()
    details_query = urlencode({"computer": computer_record.pk})

    assert response.status_code == 200
    assert computer_record.name in content
    assert computer_record.hostname in content
    assert computer_record.version in content
    assert date_format(timezone.localtime(computer_record.last_seen), "Y-m-d H:i") in content
    assert "title=\"Synchronization: Synchronization allowed\"" in content
    assert "title=\"Online\"" in content
    assert "<use href=\"#icon-check\">" in content
    assert "<use href=\"#icon-online\">" in content
    assert "<span title=\"Monitored accounts\">1</span>" in content
    assert "<span title=\"Total accounts\">1</span>" in content
    assert "title=\"Pending\"" in content
    assert "title=\"Failed\"" in content
    assert f"href=\"{reverse("core:computer_commands")}?command_computer={computer_record.pk}&amp;command_status=pending\"" in content
    assert content.count("class=\"sanea-table-item\"") == 1
    assert content.count(f"id=\"computer-details-open-{computer_record.pk}\"") == 1
    assert f"href=\"{reverse("core:computers")}?{details_query}\"" in content
    assert "hx-target=\"#computer-editor\"" in content
    assert "id=\"computer-dialog\"" in content
    assert "data-editor-dialog" in content
    assert "data-dialog-editor" in content
    assert "computer-configure-open-" not in content
    assert "computer-menu-" not in content
    assert "computer-actions-" not in content
    assert "text-bg-success" not in content
    assert "text-bg-warning" not in content
    assert "id=\"command-history\"" not in content
    assert "id=\"sanex-updates\"" not in content
    assert "role=\"tablist\"" not in content
    assert content.index("id=\"registration-window\"") < content.index("id=\"computer-list\"")
    assert "hx-trigger=\"every 5s [!document.hidden], computer-refresh[!document.hidden]\"" in content
    assert "hx-include=\"#computer-filter select\"" in content
    assert "hx-target=\"#computer-table\" hx-swap=\"outerHTML\" hx-sync=\"#computers-page:abort\"" in content
    assert "src=\"/static/sanea/js/computers.js\"" in content
    assert "src=\"/static/sanea/js/editor-dialog.js\"" in content

    for column in ("Synchronization", "Connection", "Settings", "Version", "Contact", "Commands", "Accounts"):
        assert f"data-label=\"{column}\"" in content

    for column in ("Synchronization", "Connection", "Settings"):
        assert f"<td class=\"text-center\" data-label=\"{column}\">" in content

    assert "class=\"small text-body-secondary text-center\" data-label=\"Commands\"" in content
    assert "class=\"small text-body-secondary text-nowrap text-center\" data-label=\"Accounts\"" in content


@pytest.mark.parametrize(
    ("route", "title"), [("computer_commands", "Command history"), ("computer_updates", "Updates")],
)
def test_computer_subpages_have_breadcrumbs_and_keep_computers_navigation_active(
    request_client: Callable[..., Client], user_create: Callable[..., User], route: str, title: str,
) -> None:
    response = request_client(user=user_create(attributes={"is_staff": True})).get(reverse(f"core:{route}"))
    content = response.content.decode()

    assert response.status_code == 200
    assert "<nav aria-label=\"Breadcrumbs\">" in content
    assert f"<li class=\"breadcrumb-item active\" aria-current=\"page\">{title}</li>" in content
    assert f"class=\"link-secondary\" href=\"{reverse("core:computers")}\"" in content
    assert "class=\"nav-link d-flex align-items-center gap-3 active\"" in content
    assert "id=\"computer-table\"" not in content
    assert "role=\"tablist\"" not in content


@pytest.mark.parametrize("route", ["computer_commands", "computer_updates"])
@pytest.mark.parametrize("method", ["get", "post"])
def test_computer_subpages_require_management_access(
    request_client: Callable[..., Client], user_create: Callable[..., User], route: str, method: str,
) -> None:
    url = reverse(f"core:{route}")
    anonymous = getattr(request_client(), method)(url)
    regular = getattr(request_client(user=user_create()), method)(url)

    assert anonymous.status_code == 302
    assert regular.status_code == 403


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
    assert "form-control-plaintext" in content
    assert "<form" not in content
    assert "data-dialog-panel" in content
    assert f"id=\"computer-configure-{computer_record.pk}\"" in content

    groups = content.split("<fieldset")[1:]
    assert len(groups) == 4

    for group, title in zip(groups, ("Computer", "State", "Intervals", "Technical details"), strict=True):
        assert f"<legend class=\"h6 fw-semibold mb-3\">{title}</legend>" in group
        assert "<details" not in group

    assert groups[0].count("col-sm-6") == 4
    assert groups[1].count("col-sm-4") == 6
    assert groups[2].count("col-sm-6") == 5
    assert groups[3].count("col-sm-6") == 4
    assert "Contact</label>" in groups[1]
    assert "IP address</label>" in groups[1]
    assert computer_record.certificate_fingerprint in groups[3]


@pytest.mark.parametrize("status, label", [("allowed", "Synchronization allowed"), ("pending", "Pending")])
def test_computer_readonly_details_escape_reported_text_and_show_pending_access(
    request_client: Callable[..., Client], user_create: Callable[..., User], computer_record: Computer, status: str, label: str,
) -> None:
    computer_record.name = "<img src=x onerror=alert(1)>"
    computer_record.hostname = "<script>synthetic</script>"
    computer_record.status = status
    computer_record.save(update_fields=("name", "hostname", "status", "updated"))

    response = request_client(user=user_create(attributes={"is_staff": True})).get(
        reverse("core:computers"), {"computer": computer_record.pk},
        HTTP_HX_REQUEST="true", HTTP_HX_TRIGGER=f"computer-details-{computer_record.pk}",
    )
    content = response.content.decode()

    assert response.status_code == 200
    assert escape(computer_record.name) in content
    assert escape(computer_record.hostname) in content
    assert computer_record.name not in content
    assert computer_record.hostname not in content
    assert label in content
    assert "<input" not in content
    assert "<select" not in content


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
    assert f"sudo /opt/sanex/bin/sanex register {code}" in content
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
    assert "Open registration and run the command on the new computer." in content
    assert "src=\"/static/sanea/js/registration-window.js\"" in content


def test_computers_refresh_only_the_table_through_siteajax(
    request_client: Callable[..., Client], user_create: Callable[..., User], computer_record: Computer,
) -> None:
    computer_record.last_seen = timezone.now()
    computer_record.save(update_fields=("last_seen", "updated"))

    response = request_client(user=user_create(attributes={"is_staff": True})).get(
        reverse("core:computers"), HTTP_HX_REQUEST="true", HTTP_HX_TRIGGER="computer-live-refresh",
    )
    content = response.content.decode()

    assert response.status_code == 200
    assert f"id=\"computer-connection-{computer_record.pk}\"" in content
    assert f"id=\"computer-last-contact-{computer_record.pk}\"" in content
    assert f"id=\"computer-command-counts-{computer_record.pk}\"" in content
    assert f"id=\"computer-config-status-{computer_record.pk}\"" in content
    assert "id=\"computer-table\"" in content
    assert "id=\"command-history-results\"" not in content
    assert "id=\"computer-dialog\"" not in content
    assert "id=\"computer-filter\"" not in content
    assert "hx-swap-oob" not in content
    assert "title=\"Online\"" in content
    assert "sanea-shell" not in content


def test_computers_live_refresh_adds_new_rows_and_applies_current_filters(
    request_client: Callable[..., Client],
    user_create: Callable[..., User],
    computer_record: Computer,
    time_machine: TimeMachineFixture,
) -> None:
    staff_user = user_create(attributes={"is_staff": True})
    client = request_client(user=staff_user)
    computer_record.last_seen = timezone.now()
    computer_record.save(update_fields=("last_seen", "updated"))
    query = {"access": "allowed", "connection": "online", "config_delivery": "waiting"}
    initial_response = client.get(reverse("core:computers"), query)
    computer_record.status = "blocked"
    computer_record.save(update_fields=("status", "updated"))
    new_computer = Computer.objects.create(
        hostname="newly-registered-pc",
        status="allowed",
        version="0.2.0",
        last_seen=timezone.now(),
    )
    request_options = {"HTTP_HX_REQUEST": "true", "HTTP_HX_TRIGGER": "computer-live-refresh"}

    refreshed = client.get(reverse("core:computers"), query, **request_options)
    content = refreshed.content.decode()

    assert initial_response.status_code == 200
    assert new_computer.hostname not in initial_response.content.decode()
    assert refreshed.status_code == 200
    assert new_computer.hostname in content
    assert new_computer.version in content
    assert computer_record.hostname not in content

    time_machine.shift(new_computer.sync_interval * 2 + 1)
    overdue = client.get(reverse("core:computers"), query, **request_options)

    assert overdue.status_code == 200
    assert new_computer.hostname not in overdue.content.decode()
    assert "No computers have been registered." in overdue.content.decode()


@pytest.mark.parametrize("is_staff", [False, True], ids=["regular", "staff"])
def test_computers_live_refresh_checks_management_access(
    request_client: Callable[..., Client],
    user_create: Callable[..., User],
    is_staff: bool,
) -> None:
    user = user_create(attributes={"is_staff": is_staff})

    response = request_client(user=user).get(
        reverse("core:computers"),
        HTTP_HX_REQUEST="true",
        HTTP_HX_TRIGGER="computer-live-refresh",
    )

    assert response.status_code == (200 if is_staff else 403)


def test_registration_stays_expanded_after_non_javascript_submission(
    request_client: Callable[..., Client], user_create: Callable[..., User],
    registration_window_state: tuple[RegistrationWindow, list[float]],
) -> None:
    client = request_client(user=user_create(attributes={"is_staff": True}))

    response = client.post(reverse("core:computers"), {"__submit": "registration"}, follow=True)

    assert response.status_code == 200
    assert "class=\"card mb-3 sanea-registration-panel\" open" in response.content.decode()
    assert "Registration is open" in response.content.decode()


@pytest.mark.parametrize(
    "request_headers",
    [pytest.param({}, id="page"), pytest.param({"HTTP_HX_REQUEST": "true"}, id="ajax")],
)
def test_computers_open_editor_from_details(
    request_client: Callable[..., Client],
    user_create: Callable[..., User],
    computer_record: Computer,
    request_headers: dict[str, str],
) -> None:
    staff_user = user_create(attributes={"is_staff": True})

    response = request_client(user=staff_user).get(
        reverse("core:computers"), {"computer": computer_record.pk, "edit": 1},
        HTTP_HX_TRIGGER=f"computer-configure-{computer_record.pk}",
        **request_headers,
    )
    content = response.content.decode()

    assert response.status_code == 200
    assert "id=\"computer-save\"" in content
    assert "name=\"computer-name\"" in content
    assert "name=\"computer-status\"" in content
    assert "name=\"computer-timezone\"" in content
    assert computer_record.get_display_name() in content


@pytest.mark.parametrize("filtered", [False, True], ids=["all", "allowed-only"])
def test_computers_ajax_edits_access_and_runtime_intervals(
    request_client: Callable[..., Client],
    user_create: Callable[..., User],
    computer_record: Computer,
    filtered: bool,
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
            "access": "allowed" if filtered else "",
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
    assert "Synchronization blocked" in content
    assert content.count("hx-swap-oob=\"outerHTML\"") == 1
    assert "Bedroom computer" in content
    assert "id=\"computer-save\"" not in content
    assert (f"id=\"computer-details-open-{computer_record.pk}\"" in content) is not filtered


def test_computers_save_without_javascript_and_close_without_saving(
    request_client: Callable[..., Client], user_create: Callable[..., User], computer_record: Computer,
) -> None:
    client = request_client(user=user_create(attributes={"is_staff": True}))
    url = reverse("core:computers")
    original_name = computer_record.name

    editor = client.get(url, {"computer": computer_record.pk, "edit": 1})
    closed = client.get(url)
    computer_record.refresh_from_db()

    assert editor.status_code == 200
    assert "id=\"computer-save\"" in editor.content.decode()
    assert "id=\"computer-save\"" not in closed.content.decode()
    assert computer_record.name == original_name

    saved = client.post(url, {
        "__submit": "computer",
        "computer": computer_record.pk,
        "computer-name": "Synthetic renamed computer",
        "computer-status": computer_record.status,
        "computer-timezone": computer_record.timezone,
        "computer-sync_interval": computer_record.sync_interval,
        "computer-discovery_interval": computer_record.discovery_interval,
        "computer-walk_interval": computer_record.walk_interval,
        "computer-save_interval": computer_record.save_interval,
        "computer-min_prc_duration": computer_record.min_prc_duration,
    }, follow=True)
    computer_record.refresh_from_db()

    assert saved.status_code == 200
    assert saved.redirect_chain == [(f"{url}?computer={computer_record.pk}", 302)]
    assert computer_record.name == "Synthetic renamed computer"
    assert "form-control-plaintext" in saved.content.decode()
    assert "id=\"computer-save\"" not in saved.content.decode()


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
