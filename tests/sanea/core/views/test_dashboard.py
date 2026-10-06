"""Tests for the parent dashboard."""

from urllib.parse import urlencode
import hashlib
from datetime import timedelta
from collections.abc import Callable

from django.urls import reverse
from django.utils import timezone
from sanelib.protocol import parse_event_packet
from django.test import Client

from sanea import __version__
from sanea.core.models import ClientCommand, Computer, User


def test_dashboard_requires_authenticated_management_user(
    request_client: Callable[..., Client], user_create: Callable[..., User]
) -> None:
    anonymous_response = request_client().get(reverse("core:dashboard"))
    regular_user = user_create()
    regular_response = request_client(user=regular_user).get(reverse("core:dashboard"))

    assert anonymous_response.status_code == 302
    assert anonymous_response.url.startswith(reverse("core:sign_in"))
    assert reverse("admin:index") not in anonymous_response.url
    assert regular_response.status_code == 403


def test_dashboard_uses_approved_local_layout(request_client: Callable[..., Client], user_create: Callable[..., User]) -> None:
    staff_user = user_create(attributes={"is_staff": True})

    response = request_client(user=staff_user).get(reverse("core:dashboard"))
    content = response.content.decode()

    assert response.status_code == 200
    assert "<span>sane</span><span class=\"sanea-wordmark-accent\">a</span>" in content
    assert content.count("class=\"sanea-brand-logo\"") == 3
    assert "vendor/bootstrap/bootstrap.min.css" in content
    assert "href=\"/static/sanea/favicon.svg\"" in content
    assert "vendor/htmx/htmx.min.js" in content
    assert "https://" not in content
    assert content.count("Dashboard") >= 2
    assert "People" in content
    assert f"href=\"{reverse("core:people")}\"" in content
    assert "A safer, healthier" not in content
    assert "digital wellbeing at a glance" not in content
    assert content.count(">0</p>") >= 3
    assert "Computers" in content
    assert f"href=\"{reverse("core:computers")}\"" in content
    assert "Accounts" in content
    assert f"href=\"{reverse("core:accounts")}\"" in content
    assert f"href=\"{reverse("core:limits")}\"" in content
    assert "id=\"icon-limits\"" in content
    assert f"sanea {__version__}" in content


def test_dashboard_filters_and_renders_received_activity(
    request_client: Callable[..., Client],
    user_create: Callable[..., User],
    computer_record: Computer,
    client_events_content: bytes,
) -> None:
    staff_user = user_create(attributes={"is_staff": True})
    account = computer_record.accounts.get()
    digest = hashlib.sha256(client_events_content).hexdigest()
    packet = parse_event_packet(client_events_content, digest)
    account.store_event_packet(packet, len(client_events_content), None)
    client = request_client(user=staff_user)

    response = client.get(reverse("core:dashboard"), {"period": "7-days"})
    ajax_response = client.get(
        reverse("core:dashboard"),
        {"period": "7-days"},
        HTTP_HX_REQUEST="true",
        HTTP_HX_TRIGGER="activity-filter",
    )
    content = response.content.decode()
    ajax_content = ajax_response.content.decode()

    assert response.status_code == 200
    assert "id=\"activity-filter\"" in content
    assert "vendor/chartjs/chart.umd.min.js" in content
    assert "id=\"activity-chart\"" in content
    assert "50:17" in content
    assert "yandex_browser" in content
    assert "3,137" not in content
    assert ajax_response.status_code == 200
    assert "id=\"activity-area\"" in ajax_content
    assert "sanea-shell" not in ajax_content


def test_dashboard_refreshes_operational_status(
    request_client: Callable[..., Client],
    user_create: Callable[..., User],
    computer_record: Computer,
) -> None:
    staff_user = user_create(attributes={"is_staff": True})
    now = timezone.now()
    computer_record.last_seen = now
    computer_record.save(update_fields=("last_seen", "updated"))
    overdue = Computer.objects.create(
        hostname="overdue-computer",
        last_seen=now - timedelta(seconds=900),
        sync_interval=300,
    )
    Computer.objects.create(hostname="offline-computer")
    applied_config = computer_record.materialize_config()
    computer_record.applied_config = applied_config
    computer_record.save(update_fields=("applied_config", "updated"))
    ClientCommand.objects.create(
        computer=computer_record,
        type="diagnostic",
        payload={},
    )
    ClientCommand.objects.create(
        computer=overdue,
        type="update",
        payload={},
        status="failed",
        completed=now,
    )
    client = request_client(user=staff_user)

    response = client.get(reverse("core:dashboard"))
    ajax_response = client.get(
        reverse("core:dashboard"),
        HTTP_HX_REQUEST="true",
        HTTP_HX_TRIGGER="system-status",
    )
    content = response.content.decode()
    ajax_content = ajax_response.content.decode()

    assert response.status_code == 200
    assert "id=\"system-status\"" in content
    assert "hx-trigger=\"every 10s\"" in content
    assert "id=\"system-online-count\">1</div>" in content
    assert "id=\"system-overdue-count\">1</div>" in content
    assert "id=\"system-offline-count\">1</div>" in content
    assert "id=\"system-waiting-config-count\">2</div>" in content
    assert "id=\"system-pending-command-count\">1</div>" in content
    assert "id=\"system-failed-command-count\">1</div>" in content
    assert f"href=\"{reverse("core:computers")}\"" in content
    assert (
        f"href=\"{reverse("core:computers")}?{urlencode({"config_delivery": "waiting"})}#computer-list\""
    ) in content
    assert (
        f"href=\"{reverse("core:computers")}?{urlencode({"command_status": "pending"})}#command-history\""
    ) in content
    assert (
        f"href=\"{reverse("core:computers")}?{urlencode({"command_status": "failed"})}#command-history\""
    ) in content
    assert f"href=\"{reverse("core:issues")}\"" in content
    assert ajax_response.status_code == 200
    assert "id=\"system-status\"" in ajax_content
    assert "hx-trigger=\"every 10s\"" in ajax_content
    assert "sanea-shell" not in ajax_content
