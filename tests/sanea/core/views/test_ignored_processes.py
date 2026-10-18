"""Tests for ignored process management."""

from typing import Any
from collections.abc import Callable
from html import unescape
import json
import re

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.test import Client

from sanea.core.models import Account, ActivityEvent, Computer, EventPacket, LimitsTemplate, PrcExclusion, User


@pytest.mark.parametrize("ajax", [False, True], ids=["ordinary", "ajax"])
def test_ignored_processes_requires_management_user(
    request_client: Callable[..., Client],
    user_create: Callable[..., User],
    ajax: bool,
) -> None:
    headers = {"HTTP_HX_REQUEST": "true", "HTTP_HX_TRIGGER": "ignored-process-save"} if ajax else {}
    payload = {"__submit": "exclusion", "exclusion-prc_name": "demo-denied"}

    anonymous_response = request_client().post(reverse("core:limits"), payload, **headers)
    regular_response = request_client(user=user_create()).post(reverse("core:limits"), payload, **headers)

    assert anonymous_response.status_code == 302
    assert anonymous_response.url.startswith(reverse("core:sign_in"))
    assert regular_response.status_code == 403
    assert not PrcExclusion.objects.filter(prc_name="demo-denied").exists()


def test_ignored_processes_lists_names_and_add_form(
    request_client: Callable[..., Client],
    user_create: Callable[..., User],
    ignored_process_record: PrcExclusion,
    limits_template_record: LimitsTemplate,
) -> None:
    staff_user = user_create(attributes={"is_staff": True})
    client = request_client(user=staff_user)

    response = client.get(reverse("core:limits"))
    editor_response = client.get(
        reverse("core:limits"), {"exclusion": "new"},
        HTTP_HX_REQUEST="true",
        HTTP_HX_TRIGGER="ignored-process-add",
    )

    assert response.status_code == 200
    assert ignored_process_record.prc_name in response.content.decode()
    assert "id=\"ignored-process-add\"" in response.content.decode()
    page_content = response.content.decode()
    assert "<th scope=\"col\">Status</th>" not in page_content
    assert "id=\"ignored-process-dialog\"" in page_content
    assert "data-editor-dialog" in page_content
    assert "<use href=\"#icon-plus\">" in page_content
    assert "<use href=\"#icon-edit\">" in page_content
    assert "<use href=\"#icon-trash\">" in page_content
    assert "id=\"ignored-process-save\"" not in page_content
    assert page_content.index("id=\"limits-list\"") < page_content.index("id=\"ignored-processes\"")
    assert page_content.index(limits_template_record.name) < page_content.index(ignored_process_record.prc_name)
    assert page_content.count("<h1 ") == 1
    assert "<h2 class=\"h4 fw-bold mb-0\">Ignored processes</h2>" in page_content
    process_header = page_content.split("id=\"ignored-processes\"", 1)[1].split("id=\"ignored-processes-message\"", 1)[0]
    assert "justify-content-between" in process_header
    assert "gap-2 ms-auto\" id=\"ignored-process-add\"" in process_header
    navigation = re.findall(r"<nav\b[^>]*aria-label=\"Main navigation\"[^>]*>(.*?)</nav>", page_content, re.S)
    assert navigation
    assert all("Settings" not in content for content in navigation)
    assert f"href=\"{reverse('core:limits')}?exclusion=new#ignored-processes\"" in page_content
    assert editor_response.status_code == 200
    assert "data-dialog-panel" in editor_response.content.decode()
    assert "data-dialog-close" in editor_response.content.decode()
    assert "name=\"exclusion-prc_name\"" in editor_response.content.decode()
    assert "data-select-suggestions=\"[]\"" in editor_response.content.decode()
    assert "<input type=\"text\"" in editor_response.content.decode()
    assert "id=\"limits-list\"" not in editor_response.content.decode()
    assert "id=\"limits-save\"" not in editor_response.content.decode()


@pytest.mark.parametrize("ajax", [False, True], ids=["ordinary", "ajax"])
def test_ignored_process_suggestions_use_recent_global_process_names(
    request_client: Callable[..., Client], user_create: Callable[..., User],
    computer_record: Computer, ignored_process_record: PrcExclusion, ajax: bool,
) -> None:
    account = computer_record.accounts.get()
    PrcExclusion.objects.create(prc_name="released-tool", apply=False)
    values = [
        (f"synthetic-{index}", index, "prc_start") for index in range(100, 155)
    ] + [
        ("synthetic-154", 900, "prc_start"),
        ("a" * 15, 996, "prc_start"),
        ("released-tool", 997, "prc_start"),
        ('qa&"<x>', 998, "prc_start"),
        (ignored_process_record.prc_name, 2000, "prc_start"),
        ("x" * 16, 2000, "prc_start"),
        ("not-a-start", 2000, "prc_end"),
        (None, 1, "prc_start"), ("", 1, "prc_start"), ("   ", 1, "prc_start"),
    ]
    packet = EventPacket.objects.create(
        account=account, sha256="a" * 64, first_seq=1, last_seq=len(values), event_count=len(values), byte_size=100,
    )
    ActivityEvent.objects.bulk_create(
        ActivityEvent(account=account, packet=packet, seq=index, timestamp=timestamp, type=kind, prc_name=name)
        for index, (name, timestamp, kind) in enumerate(values, start=1)
    )
    other_computer = Computer.objects.create(hostname="synthetic-other", name="Synthetic other")
    other_account = Account.objects.create(computer=other_computer, uid=1002, login="synthetic")
    other_packet = EventPacket.objects.create(
        account=other_account, sha256="b" * 64, first_seq=1, last_seq=1, event_count=1, byte_size=100,
    )
    ActivityEvent.objects.create(
        account=other_account, packet=other_packet, seq=1, timestamp=999, type="prc_start", prc_name="remote-tool",
        app_id="desktop:synthetic.Other", app_name="Synthetic application name",
    )
    client = request_client(user=user_create(attributes={"is_staff": True}))
    headers = {"HTTP_HX_REQUEST": "true", "HTTP_HX_TRIGGER": "ignored-process-add"} if ajax else {}

    with CaptureQueriesContext(connection) as queries:
        response = client.get(reverse("core:limits"), {"exclusion": "new"}, **headers)

    content = response.content.decode()
    input_tag = re.search(r'<input\b[^>]*name="exclusion-prc_name"[^>]*>', content).group()
    encoded_values = re.search(r'data-select-suggestions="([^"]*)"', input_tag).group(1)
    suggestions = json.loads(unescape(encoded_values))
    activity_queries = [query for query in queries if 'FROM "core_activityevent"' in query["sql"]]

    assert response.status_code == 200
    assert len(activity_queries) == 1
    assert len(suggestions) == 50
    assert suggestions[:5] == ["remote-tool", 'qa&"<x>', "released-tool", "a" * 15, "synthetic-154"]
    assert suggestions.count("synthetic-154") == 1
    assert "synthetic-109" in suggestions
    assert "synthetic-108" not in suggestions
    assert ignored_process_record.prc_name not in suggestions
    assert "x" * 16 not in suggestions
    assert "not-a-start" not in suggestions
    assert "Synthetic application name" not in suggestions
    assert 'qa&"<x>' not in input_tag


@pytest.mark.parametrize("ajax", [False, True], ids=["ordinary", "ajax"])
def test_ignored_process_suggestion_saves_the_exact_recorded_name(
    request_client: Callable[..., Client], user_create: Callable[..., User], computer_record: Computer,
    activity_run_create: Callable[..., None], ajax: bool,
) -> None:
    activity_run_create(
        computer_record.accounts.get(), started=100, finished=None, kind="prc", prc_name="SteamWebHelper",
        application={"ident": "steam:client", "name": "Steam"},
    )
    client = request_client(user=user_create(attributes={"is_staff": True}))
    headers = {"HTTP_HX_REQUEST": "true", "HTTP_HX_TRIGGER": "ignored-process-save"} if ajax else {}

    response = client.post(reverse("core:limits"), {
        "__submit": "exclusion", "exclusion": "new", "exclusion-prc_name": "SteamWebHelper",
    }, **headers)

    assert response.status_code == (200 if ajax else 302)
    assert PrcExclusion.objects.get(prc_name="SteamWebHelper").apply


@pytest.mark.parametrize("ajax", [False, True], ids=["ordinary", "ajax"])
def test_ignored_processes_adds_removes_and_restores_names(
    request_client: Callable[..., Client],
    user_create: Callable[..., User],
    ignored_process_record: PrcExclusion,
    ignored_processes_payload: dict[str, Any],
    ajax: bool,
) -> None:
    staff_user = user_create(attributes={"is_staff": True})
    client = request_client(user=staff_user)
    created_name = ignored_processes_payload["created"]["prc_name"]
    headers = {"HTTP_HX_REQUEST": "true"} if ajax else {}

    create_response = client.post(
        reverse("core:limits"),
        {
            "__submit": "exclusion",
            "exclusion-prc_name": created_name,
        },
        HTTP_HX_TRIGGER="ignored-process-save",
        **headers,
    )

    assert create_response.status_code == (200 if ajax else 302)
    assert PrcExclusion.objects.filter(prc_name=created_name).exists()

    if ajax:
        assert created_name in create_response.content.decode()
        assert "id=\"ignored-processes-list\" hx-swap-oob=\"outerHTML\"" in create_response.content.decode()
        assert "id=\"limits-list\"" not in create_response.content.decode()
        assert "data-dialog-panel" not in create_response.content.decode()

    else:
        assert create_response.url == f"{reverse('core:limits')}#ignored-processes"

    delete_response = client.post(
        reverse("core:limits"),
        {
            "delete": "1",
            "exclusion": f"{ignored_process_record.pk}",
        },
        HTTP_HX_TRIGGER=f"ignored-process-delete-{ignored_process_record.pk}",
        **headers,
    )

    assert delete_response.status_code == (200 if ajax else 302)
    ignored_process_record.refresh_from_db()
    assert ignored_process_record.apply is False

    assert f"<code>{ignored_process_record.prc_name}</code>" not in delete_response.content.decode()

    restore_response = client.post(
        reverse("core:limits"),
        {
            "__submit": "exclusion",
            "exclusion-prc_name": ignored_process_record.prc_name,
        },
        HTTP_HX_TRIGGER="ignored-process-save",
        **headers,
    )
    ignored_process_record.refresh_from_db()

    assert restore_response.status_code == (200 if ajax else 302)
    assert ignored_process_record.apply is True


@pytest.mark.parametrize("ajax", [False, True])
def test_ignored_process_dialog_edits_name_and_updates_computer_config(
    request_client: Callable[..., Client], user_create: Callable[..., User], ignored_process_record: PrcExclusion,
    computer_record: Computer, ajax: bool,
) -> None:
    client = request_client(user=user_create(attributes={"is_staff": True}))
    headers = {"HTTP_HX_REQUEST": "true"} if ajax else {}
    original_name = ignored_process_record.prc_name

    editor = client.get(
        reverse("core:limits"), {"exclusion": ignored_process_record.pk},
        HTTP_HX_TRIGGER=f"ignored-process-edit-{ignored_process_record.pk}", **headers,
    )
    response = client.post(
        reverse("core:limits"),
        {"__submit": "exclusion", "exclusion": ignored_process_record.pk, "exclusion-prc_name": "demo-renamed"},
        HTTP_HX_TRIGGER="ignored-process-save", **headers,
    )
    ignored_process_record.refresh_from_db()
    computer_record.refresh_from_db()

    assert editor.status_code == 200
    assert "data-dialog-panel" in editor.content.decode()
    assert "id=\"limits-save\"" not in editor.content.decode()
    assert f"value=\"{original_name}\"" in editor.content.decode()
    assert response.status_code == (200 if ajax else 302)
    assert ignored_process_record.prc_name == "demo-renamed"
    assert "demo-renamed" in computer_record.current_config.decode().ignored_prcs
    assert original_name not in computer_record.current_config.decode().ignored_prcs


@pytest.mark.parametrize("ajax", [False, True])
@pytest.mark.parametrize("invalid_name", ["", "x" * 16, "nautilus"])
def test_ignored_process_dialog_preserves_invalid_input_without_saving(
    request_client: Callable[..., Client], user_create: Callable[..., User], ignored_process_record: PrcExclusion,
    invalid_name: str, ajax: bool,
) -> None:
    client = request_client(user=user_create(attributes={"is_staff": True}))
    original_name = ignored_process_record.prc_name
    headers = {"HTTP_HX_REQUEST": "true", "HTTP_HX_TRIGGER": "ignored-process-save"} if ajax else {}

    response = client.post(
        reverse("core:limits"),
        {"__submit": "exclusion", "exclusion": ignored_process_record.pk, "exclusion-prc_name": invalid_name},
        **headers,
    )
    ignored_process_record.refresh_from_db()
    content = response.content.decode()

    assert response.status_code == 200
    assert "data-dialog-panel" in content
    assert "is-invalid" in content
    assert "id=\"limits-save\"" not in content
    name_input = re.search(r"<input\b[^>]*name=\"exclusion-prc_name\"[^>]*>", content).group()
    assert "".join(re.findall(r"\bvalue=\"([^\"]*)\"", name_input)) == invalid_name
    assert ignored_process_record.prc_name == original_name

    if not ajax:
        assert "id=\"limits-list\"" in content
        assert "id=\"ignored-processes\"" in content


def test_ignored_process_cancel_does_not_save_and_removed_rows_are_not_listed(
    request_client: Callable[..., Client], user_create: Callable[..., User], ignored_process_record: PrcExclusion,
) -> None:
    removed = PrcExclusion.objects.create(prc_name="demo-removed", apply=False)
    client = request_client(user=user_create(attributes={"is_staff": True}))

    cancelled = client.get(
        reverse("core:limits"), HTTP_HX_REQUEST="true", HTTP_HX_TRIGGER="ignored-process-cancel",
    )
    response = client.get(reverse("core:limits"))
    missing_editor = client.get(
        reverse("core:limits"), {"exclusion": removed.pk},
        HTTP_HX_REQUEST="true", HTTP_HX_TRIGGER=f"ignored-process-edit-{removed.pk}",
    )
    ignored_process_record.refresh_from_db()

    assert cancelled.status_code == 200
    assert cancelled.content == b""
    assert missing_editor.status_code == 404
    assert removed.prc_name not in response.content.decode()
    assert ignored_process_record.apply is True
