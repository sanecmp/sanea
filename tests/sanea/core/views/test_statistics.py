"""Tests for the dedicated activity statistics page."""

import hashlib
from collections.abc import Callable

import pytest
from django.test import Client
from django.urls import reverse
from sanelib.protocol import parse_event_packet

from sanea.core.models import Computer, User


@pytest.mark.parametrize(
    "request_options",
    [{}, {"HTTP_HX_REQUEST": "true", "HTTP_HX_TRIGGER": "activity-filter"}],
    ids=["page", "fragment"],
)
def test_statistics_requires_authenticated_management_user(
    request_client: Callable[..., Client],
    user_create: Callable[..., User],
    request_options: dict[str, str],
) -> None:
    regular_user = user_create()

    anonymous = request_client().get(reverse("core:statistics"), **request_options)
    regular = request_client(user=regular_user).get(reverse("core:statistics"), **request_options)

    assert anonymous.status_code == 302
    assert anonymous.url.startswith(reverse("core:sign_in"))
    assert regular.status_code == 403


def test_statistics_filters_and_renders_received_activity(
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
    filters = {"period": "7-days", "computer": computer_record.pk, "account": account.pk}

    response = client.get(reverse("core:statistics"), filters)
    ajax_response = client.get(
        reverse("core:statistics"), filters,
        HTTP_HX_REQUEST="true", HTTP_HX_TRIGGER="activity-filter",
    )
    content = response.content.decode()
    ajax_content = ajax_response.content.decode()

    assert response.status_code == 200
    assert "Statistics" in content
    assert "id=\"activity-filter\"" in content
    assert f"action=\"{reverse("core:statistics")}\"" in content
    assert f"hx-get=\"{reverse("core:statistics")}\"" in content
    assert "id=\"system-status\"" not in content
    assert "sanea-summary-card" not in content
    assert "vendor/chartjs/chart.umd.min.js" in content
    assert "sanea/js/activity-chart.js" in content
    assert "id=\"activity-chart\"" in content
    assert "50:17" in content
    assert "yandex_browser" in content
    assert "Launches" in content
    assert "Application usage" in content
    assert "3,137" not in content
    assert ajax_response.status_code == 200
    assert "id=\"activity-area\"" in ajax_content
    assert "yandex_browser" in ajax_content
    assert "sanea-shell" not in ajax_content


def test_statistics_renders_an_empty_report_without_operational_blocks(
    request_client: Callable[..., Client],
    user_create: Callable[..., User],
) -> None:
    staff_user = user_create(attributes={"is_staff": True})

    response = request_client(user=staff_user).get(reverse("core:statistics"))
    content = response.content.decode()

    assert response.status_code == 200
    assert "No application use was recorded for this period." in content
    assert "No screen time was recorded for this period." in content
    assert "Correct the filters to view activity." not in content
    assert "id=\"system-status\"" not in content


@pytest.mark.parametrize(
    "request_options",
    [{}, {"HTTP_HX_REQUEST": "true", "HTTP_HX_TRIGGER": "activity-filter"}],
    ids=["page", "fragment"],
)
def test_statistics_rejects_invalid_filters(
    request_client: Callable[..., Client],
    user_create: Callable[..., User],
    request_options: dict[str, str],
) -> None:
    staff_user = user_create(attributes={"is_staff": True})

    response = request_client(user=staff_user).get(
        reverse("core:statistics"), {"period": "invalid"}, **request_options,
    )
    content = response.content.decode()

    assert response.status_code == 200
    assert "Correct the filters to view activity." in content
    assert "id=\"activity-chart\"" not in content
