"""Tests for application rule management."""

import hashlib
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from django.test import Client
from django.urls import reverse

from sanea.core.models import (
    Account,
    ActivityEvent,
    AppRule,
    Computer,
    EventPacket,
    Limits,
    LimitsTemplate,
    Person,
    SessionRule,
    User,
)


def _app_rules_url(limits: Limits, session_rule: SessionRule) -> str:
    return reverse("core:app_rules", kwargs={"limits_pk": limits.pk, "rule_pk": session_rule.pk})


@pytest.mark.parametrize(
    "request_options",
    [{}, {"HTTP_HX_REQUEST": "true", "HTTP_HX_TRIGGER": "app-rule-add"}],
    ids=["page", "fragment"],
)
def test_app_rules_requires_management_user(
    request_client: Callable[..., Client],
    user_create: Callable[..., User],
    limits_record: Limits,
    session_rule_record: SessionRule,
    request_options: dict[str, str],
) -> None:
    url = _app_rules_url(limits_record, session_rule_record)
    anonymous_response = request_client().get(url, {"app_rule": "new"}, **request_options)
    regular_response = request_client(user=user_create()).get(url, {"app_rule": "new"}, **request_options)

    assert anonymous_response.status_code == 302
    assert anonymous_response.url.startswith(reverse("core:sign_in"))
    assert regular_response.status_code == 403


@pytest.fixture
def recorded_applications(computer_record: Computer, datafix_dir: Path) -> Account:
    """Store synthetic suggestions, including duplicate and empty database values."""
    account = computer_record.accounts.get()
    content = (datafix_dir / "app_suggestions.json").read_bytes()
    values = json.loads(content)
    packet = EventPacket.objects.create(
        account=account,
        sha256=hashlib.sha256(content).hexdigest(),
        first_seq=1,
        last_seq=len(values),
        event_count=len(values),
        byte_size=len(content),
    )
    ActivityEvent.objects.bulk_create(
        ActivityEvent(
            account=account,
            packet=packet,
            seq=index,
            type="prc_start",
            timestamp=index,
            **value,
        )
        for index, value in enumerate(values, start=1)
    )
    return account


@pytest.mark.parametrize("template_scope", [False, True], ids=["account", "template"])
@pytest.mark.parametrize(
    "request_options",
    [{}, {"HTTP_HX_REQUEST": "true", "HTTP_HX_TRIGGER": "app-rule-add"}],
    ids=["page", "fragment"],
)
def test_app_rules_suggest_scoped_recorded_processes(
    request_client: Callable[..., Client],
    user_create: Callable[..., User],
    recorded_applications: Account,
    limits_record: Limits,
    session_rule_record: SessionRule,
    template_scope: bool,
    request_options: dict[str, str],
) -> None:
    account = recorded_applications

    if template_scope:
        template = LimitsTemplate.objects.create(name="New version", current_limits=limits_record)
        account.person = Person.objects.create(name="Child", limits_tpl=template)
        account.limits = Limits.objects.create(name="Assigned old version")

    else:
        account.limits = limits_record

    account.save(update_fields=("person", "limits", "updated"))
    other_account = Account.objects.create(
        computer=account.computer, uid=1002, login="other", name="Other",
        person=Person.objects.create(name="Other child"),
    )
    other_packet = EventPacket.objects.create(
        account=other_account, sha256="f" * 64, first_seq=1, last_seq=1, event_count=1, byte_size=100,
    )
    ActivityEvent.objects.create(
        account=other_account, packet=other_packet, seq=1, type="prc_start", timestamp=100,
        prc_name="other_application", exe="/opt/other_application",
    )
    staff_user = user_create(attributes={"is_staff": True})

    response = request_client(user=staff_user).get(
        _app_rules_url(limits_record, session_rule_record), {"app_rule": "new"}, **request_options,
    )
    content = response.content.decode()

    assert response.status_code == 200
    assert "list=\"id_app_rule-prc_name-suggestions\"" in content
    assert "list=\"id_app_rule-exe-suggestions\"" in content
    assert "<datalist id=\"id_app_rule-prc_name-suggestions\">" in content
    assert "<datalist id=\"id_app_rule-exe-suggestions\">" in content
    assert content.count("<option value=\"reader&amp;&quot;&lt;app&gt;\"></option>") == 1
    assert content.count("<option value=\"/opt/reader&amp;&quot;/&lt;app&gt;\"></option>") == 1
    assert "<option value=\"browser\"></option>" in content
    assert "<option value=\"/usr/bin/browser\"></option>" in content
    assert "<option value=\"\"></option>" not in content
    assert "<option value=\"   \"></option>" not in content
    assert "other_application" not in content
    assert "wnd_title-suggestions" not in content


def test_app_rules_suggestions_are_bounded_and_newest_first(
    request_client: Callable[..., Client],
    user_create: Callable[..., User],
    recorded_applications: Account,
    limits_record: Limits,
    session_rule_record: SessionRule,
) -> None:
    account = recorded_applications
    account.limits = limits_record
    account.save(update_fields=("limits", "updated"))
    packet = account.event_packets.get()
    ActivityEvent.objects.bulk_create(
        ActivityEvent(
            account=account,
            packet=packet,
            seq=index,
            timestamp=index,
            type="prc_start",
            prc_name=f"app-{index}",
            exe=f"/opt/app-{index}",
        )
        for index in range(100, 155)
    )
    ActivityEvent.objects.create(
        account=account, packet=packet, seq=200, timestamp=200, type="prc_start",
        prc_name="x" * 257, exe="/" + "x" * 4096,
    )
    staff_user = user_create(attributes={"is_staff": True})

    response = request_client(user=staff_user).get(
        _app_rules_url(limits_record, session_rule_record), {"app_rule": "new"},
    )
    content = response.content.decode()
    process_options = content.partition("<datalist id=\"id_app_rule-prc_name-suggestions\">")[2].partition("</datalist>")[0]
    executable_options = content.partition("<datalist id=\"id_app_rule-exe-suggestions\">")[2].partition("</datalist>")[0]

    assert response.status_code == 200
    assert process_options.count("<option") == 50
    assert executable_options.count("<option") == 50
    assert process_options.index("value=\"app-154\"") < process_options.index("value=\"app-153\"")
    assert "value=\"app-105\"" in process_options
    assert "value=\"app-104\"" not in process_options
    assert executable_options.index("value=\"/opt/app-154\"") < executable_options.index("value=\"/opt/app-153\"")
    assert "x" * 257 not in process_options
    assert "/" + "x" * 4096 not in executable_options


def test_app_rules_without_scoped_activity_keep_manual_inputs(
    request_client: Callable[..., Client],
    user_create: Callable[..., User],
    recorded_applications: Account,
    limits_record: Limits,
    session_rule_record: SessionRule,
) -> None:
    staff_user = user_create(attributes={"is_staff": True})

    response = request_client(user=staff_user).get(
        _app_rules_url(limits_record, session_rule_record), {"app_rule": "new"},
    )
    content = response.content.decode()

    assert response.status_code == 200
    assert "<input type=\"text\"" in content
    assert "-suggestions" not in content
    assert "suggestions from recorded activity" not in content


def test_app_rules_suggestions_allow_manual_values_with_matching_validation(
    request_client: Callable[..., Client],
    user_create: Callable[..., User],
    recorded_applications: Account,
    limits_record: Limits,
    session_rule_record: SessionRule,
) -> None:
    account = recorded_applications
    account.limits = limits_record
    account.save(update_fields=("limits", "updated"))
    staff_user = user_create(attributes={"is_staff": True})
    client = request_client(user=staff_user)
    url = _app_rules_url(limits_record, session_rule_record)
    payload = {
        "__submit": "app_rule",
        "app_rule": "new",
        "app_rule-name": "Manual application",
        "app_rule-apply": "on",
        "app_rule-max_launches": "3",
        "app_rule-prc_name": "previously_unseen_application",
    }
    request_options = {"HTTP_HX_REQUEST": "true", "HTTP_HX_TRIGGER": "app-rule-save"}

    invalid = client.post(url, payload, **request_options)
    content = invalid.content.decode()

    assert invalid.status_code == 200
    assert "A matching method is required." in content
    assert "value=\"previously_unseen_application\"" in content
    assert "<datalist id=\"id_app_rule-prc_name-suggestions\">" in content
    assert not AppRule.objects.filter(name="Manual application").exists()

    saved = client.post(url, {**payload, "app_rule-prc_name_match": "exact"}, **request_options)
    rule = AppRule.objects.get(name="Manual application")

    assert saved.status_code == 200
    assert rule.prc_name == "previously_unseen_application"
    assert rule.prc_name_match == "exact"
    assert rule.max_launches == 3


def test_app_rules_list_session_members(
    request_client: Callable[..., Client],
    user_create: Callable[..., User],
    limits_record: Limits,
    session_rule_record: SessionRule,
    app_rule_record: AppRule,
) -> None:
    staff_user = user_create(attributes={"is_staff": True})

    response = request_client(user=staff_user).get(
        _app_rules_url(limits_record, session_rule_record)
    )
    content = response.content.decode()

    assert response.status_code == 200
    assert session_rule_record.name in content
    assert app_rule_record.name in content
    assert app_rule_record.prc_name in content
    assert "id=\"app-rule-add\"" in content
    assert f"id=\"app-rule-edit-{app_rule_record.pk}\"" in content


def test_app_rules_ajax_create_and_update(
    request_client: Callable[..., Client],
    user_create: Callable[..., User],
    limits_record: Limits,
    session_rule_record: SessionRule,
    app_rule_record: AppRule,
    app_rules_payload: dict[str, Any],
) -> None:
    staff_user = user_create(attributes={"is_staff": True})
    client = request_client(user=staff_user)
    url = _app_rules_url(limits_record, session_rule_record)
    ajax_headers = {
        "HTTP_HX_REQUEST": "true",
        "HTTP_HX_TRIGGER": "app-rule-save",
    }
    created = app_rules_payload["created"]

    create_response = client.post(
        url,
        {
            "__submit": "app_rule",
            "app_rule": "new",
            "app_rule-name": created["name"],
            "app_rule-apply": "on",
            "app_rule-max_launches": f"{created["max_launches"]}",
            "app_rule-max_time": f"{created["max_time"]}",
            "app_rule-exe": created["exe"],
            "app_rule-exe_match": created["exe_match"],
            "app_rule-wnd_title": created["wnd_title"],
            "app_rule-wnd_title_match": created["wnd_title_match"],
        },
        **ajax_headers,
    )
    created_rule = AppRule.objects.get(
        session_rule=session_rule_record,
        name=created["name"],
    )

    assert create_response.status_code == 200
    assert created_rule.ident == app_rule_record.ident + 1
    assert "hx-swap-oob=\"outerHTML\"" in create_response.content.decode()

    update_response = client.post(
        url,
        {
            "__submit": "app_rule",
            "app_rule": f"{app_rule_record.pk}",
            "app_rule-name": app_rules_payload["renamed"]["name"],
            "app_rule-max_launches": f"{app_rule_record.max_launches}",
            "app_rule-max_time": f"{app_rule_record.max_time}",
            "app_rule-prc_name": app_rule_record.prc_name,
            "app_rule-prc_name_match": app_rule_record.prc_name_match,
        },
        **ajax_headers,
    )
    app_rule_record.refresh_from_db()

    assert update_response.status_code == 200
    assert app_rule_record.name == app_rules_payload["renamed"]["name"]
    assert app_rule_record.apply is False


def test_app_rule_accepts_time_limit_without_launch_limit(
    request_client: Callable[..., Client],
    user_create: Callable[..., User],
    limits_record: Limits,
    session_rule_record: SessionRule,
) -> None:
    staff_user = user_create(attributes={"is_staff": True})
    response = request_client(user=staff_user).post(
        _app_rules_url(limits_record, session_rule_record),
        {
            "__submit": "app_rule",
            "app_rule": "new",
            "app_rule-name": "Time only",
            "app_rule-apply": "on",
            "app_rule-max_launches": "",
            "app_rule-max_time": "1800",
            "app_rule-prc_name": "browser",
            "app_rule-prc_name_match": "exact",
        },
        HTTP_HX_REQUEST="true",
        HTTP_HX_TRIGGER="app-rule-save",
    )

    assert response.status_code == 200
    created = AppRule.objects.get(name="Time only")
    assert created.max_launches is None
    assert created.max_time == 1800
