"""Tests for one account's combined, independently saved limits card."""

import hashlib
import re
from collections.abc import Callable
from urllib.parse import urlsplit

import pytest
from django.test import Client
from django.urls import reverse
from sanelib.protocol import parse_event_packet

from sanea.core.forms.account_limits import AccountLimitsForm
from sanea.core.models import (
    Account, ActivityEvent, AppRule, Computer, ComputerConfig, IdentifierSequence,
    Limits, LimitsTemplate, Person, Range, SessionRule, User,
)


@pytest.fixture
def limits_card_account(
    computer_record: Computer,
    person_record: Person,
    range_record: Range,
    app_rule_record: AppRule,
) -> Account:
    account = computer_record.accounts.get()
    account.person = person_record
    account.limits = range_record.limits
    account.collect = False
    account.save(update_fields=("person", "limits", "collect", "updated"))
    return account


def encode_card_value(value: object) -> str:

    if value is None:
        return ""

    if isinstance(value, bool):
        return "on" if value else ""

    return f"{value}"


def build_card_post(account: Account) -> dict[str, str]:
    """Submit rendered values, including second precision and blank extra rows."""
    controls = AccountLimitsForm(account=account)
    forms = [controls]

    for formset in (controls.sessions, controls.ranges, controls.apps):
        forms.extend((formset.management_form, *formset.forms))

    return {field.html_name: encode_card_value(field.value()) for form in forms for field in form}


def read_limits_state() -> dict[str, object]:
    """Include configuration and identifier writes in atomicity checks."""
    models = (Account, Limits, SessionRule, Range, AppRule, LimitsTemplate, Computer, ComputerConfig, IdentifierSequence)
    return {model.__name__: tuple(model.objects.order_by("pk").values()) for model in models}


@pytest.mark.parametrize("method", ["get", "post"])
def test_account_limits_requires_management_user(
    request_client: Callable[..., Client],
    user_create: Callable[..., User],
    computer_record: Computer,
    method: str,
) -> None:
    url = reverse("core:account_limits", args=(computer_record.accounts.get().pk,))
    regular_user = user_create()

    anonymous_response = getattr(request_client(), method)(url)
    regular_response = getattr(request_client(user=regular_user), method)(url)

    assert anonymous_response.status_code == 302
    assert anonymous_response.url.startswith(reverse("core:sign_in"))
    assert regular_response.status_code == 403


def test_account_limits_get_preserves_graph_and_scopes_choices_and_suggestions(
    request_client: Callable[..., Client],
    user_create: Callable[..., User],
    limits_card_account: Account,
    limits_template_record: LimitsTemplate,
    client_events_content: bytes,
) -> None:
    account = limits_card_account
    account.collect = True
    account.save(update_fields=("collect", "updated"))
    sibling = Account.objects.create(
        computer=account.computer, person=account.person, limits=account.limits,
        uid=1002, login="sibling", name="Sibling account", collect=True,
    )
    other_person = Person.objects.create(name="Other child")
    other_account = Account.objects.create(
        computer=account.computer, person=other_person, uid=1003, login="other", name="Other account",
    )
    packet = parse_event_packet(client_events_content, hashlib.sha256(client_events_content).hexdigest())
    account.store_event_packet(packet, len(client_events_content), None)
    ActivityEvent.objects.filter(account=account, type="enforcement_failed").update(prc_name="synthetic_non_start")
    sibling_content = client_events_content.replace(b"yandex_browser", b"sibling_application")
    sibling_packet = parse_event_packet(sibling_content, hashlib.sha256(sibling_content).hexdigest())
    sibling.store_event_packet(sibling_packet, len(sibling_content), None)
    staff_user = user_create(attributes={"is_staff": True})
    before = read_limits_state()

    response = request_client(user=staff_user).get(reverse("core:account_limits", args=(account.pk,)))
    content = response.content.decode()

    assert response.status_code == 200
    assert f"href=\"{reverse("core:account_limits", args=(sibling.pk,))}\"" in content
    assert f"href=\"{reverse("core:account_limits", args=(other_account.pk,))}\"" not in content
    assert "yandex_browser" in content
    assert "sibling_application" not in content
    assert "synthetic_non_start" not in content
    assert "name=\"limits-limits_version\"" in content
    assert "name=\"sessions-0-id\"" in content
    assert "name=\"ranges-0-id\"" in content
    assert "name=\"apps-0-id\"" in content
    assert "name=\"sessions-0-max_duration\"" in content
    assert "name=\"ranges-0-rule\"" in content
    assert "name=\"apps-0-max_time\"" in content
    checkbox_labels = re.findall(r"<label class=\"form-check-label\"[^>]*>([^<]*)</label>", content)
    assert checkbox_labels
    assert all(not label.rstrip().endswith(":") for label in checkbox_labels)
    assert "class=\"form-check-input\"" in content
    assert "class=\"form-control\"" in content
    assert "aria-describedby=\"id_sessions-0-max_duration_help\"" in content
    assert "id=\"id_sessions-0-max_duration_help\"" in content
    assert "data-delete-field" in content
    assert "data-rule-deletion" in content
    assert f"form=\"account-remove-sessions-{account.limits.session_rules.get().pk}\"" in content
    sessions_markup = content.split("id=\"account-limits-sessions\"", 1)[1].split("id=\"account-limits-apps\"", 1)[0]
    assert sessions_markup.index("data-add-form") < sessions_markup.index("data-form-rows")
    assert read_limits_state() == before


@pytest.mark.parametrize(
    "collect, duration, discard_extra",
    [
        pytest.param(False, 7200, False, id="unchanged"),
        pytest.param(False, 1, False, id="one-second"),
        pytest.param(True, 59, False, id="monitoring-only-59-seconds"),
        pytest.param(False, 7200, True, id="discard-blank-extra-rows"),
    ],
)
def test_account_limits_preserves_shared_snapshot_without_graph_changes(
    request_client: Callable[..., Client],
    user_create: Callable[..., User],
    limits_card_account: Account,
    limits_template_record: LimitsTemplate,
    collect: bool,
    duration: int,
    discard_extra: bool,
) -> None:
    account = limits_card_account
    source = account.limits
    source.session_rules.update(max_duration=duration)
    original_graph = source.build_client_config()
    data = build_card_post(account)
    data["limits-collect"] = encode_card_value(collect)
    data.update({f"{prefix}-1-DELETE": encode_card_value(discard_extra) for prefix in ("sessions", "ranges", "apps")})
    staff_user = user_create(attributes={"is_staff": True})

    response = request_client(user=staff_user).post(reverse("core:account_limits", args=(account.pk,)), data)
    account.refresh_from_db()
    limits_template_record.refresh_from_db()

    assert response.status_code == 302
    assert urlsplit(response.url).path == reverse("core:account_limits", args=(account.pk,))
    assert account.collect is collect
    assert account.limits_id == source.pk
    assert limits_template_record.current_limits_id == source.pk
    assert Limits.objects.count() == 1
    assert source.build_client_config() == original_graph


def test_account_limits_combined_save_forks_only_selected_account_and_preserves_identities(
    request_client: Callable[..., Client],
    user_create: Callable[..., User],
    limits_card_account: Account,
    limits_template_record: LimitsTemplate,
) -> None:
    account = limits_card_account
    source = account.limits
    original_graph = source.build_client_config()
    other_computer = Computer.objects.create(hostname="other-pc", status="allowed", timezone="Asia/Novosibirsk")
    other_account = Account.objects.create(computer=other_computer, limits=source, uid=1001, login="other", name="Other")
    other_config = other_computer.materialize_config()
    previous_config = account.computer.materialize_config()
    data = build_card_post(account)
    data.update({
        "limits-apply": "on",
        "sessions-0-max_duration": "60", "sessions-0-break_duration": "15",
        "ranges-0-since": "14:00", "ranges-0-till": "19:00", "apps-0-max_time": "30",
    })
    staff_user = user_create(attributes={"is_staff": True})

    response = request_client(user=staff_user).post(reverse("core:account_limits", args=(account.pk,)), data)
    account.refresh_from_db()
    other_account.refresh_from_db()
    other_computer.refresh_from_db()
    account.computer.refresh_from_db()
    limits_template_record.refresh_from_db()
    session = account.limits.session_rules.get()
    range_ = account.limits.ranges.get()
    app = session.app_rules.get()

    assert response.status_code == 302
    assert account.apply is True
    assert account.collect is True
    assert account.limits_id != source.pk
    assert limits_template_record.current_limits_id == source.pk
    assert other_account.limits_id == source.pk
    assert source.build_client_config() == original_graph
    assert (session.ident, range_.ident, app.ident) == (11, 31, 21)
    assert (session.max_duration, session.break_duration, app.max_time) == (3600, 900, 1800)
    assert (range_.since, range_.till, range_.session_rule_id) == (840, 1140, session.pk)
    assert other_computer.current_config_id == other_config.pk
    assert account.computer.current_config_id != previous_config.pk


def test_account_limits_creates_session_range_and_application_in_one_save(
    request_client: Callable[..., Client],
    user_create: Callable[..., User],
    computer_record: Computer,
) -> None:
    account = computer_record.accounts.get()
    account.name = ""
    account.collect = False
    account.save(update_fields=("name", "collect", "updated"))
    data = build_card_post(account)
    data.update({
        "limits-apply": "on",
        "sessions-TOTAL_FORMS": "1", "ranges-TOTAL_FORMS": "1", "apps-TOTAL_FORMS": "1",
        "sessions-0-name": "Play time", "sessions-0-apply": "on", "sessions-0-max_sessions": "2",
        "sessions-0-max_duration": "60", "sessions-0-break_duration": "15",
        "ranges-0-apply": "on", "ranges-0-weekday": "5", "ranges-0-since": "15:00",
        "ranges-0-till": "18:00", "ranges-0-rule": "0",
        "apps-0-name": "Browser", "apps-0-apply": "on", "apps-0-max_time": "30",
        "apps-0-prc_name": "browser", "apps-0-prc_name_match": "exact", "apps-0-rule": "0",
    })
    staff_user = user_create(attributes={"is_staff": True})

    response = request_client(user=staff_user).post(reverse("core:account_limits", args=(account.pk,)), data)
    account.refresh_from_db()
    computer_record.refresh_from_db()
    session = account.limits.session_rules.get()
    range_ = account.limits.ranges.get()
    app = session.app_rules.get()

    assert response.status_code == 302
    assert account.apply is True
    assert account.collect is True
    assert session.name == "Play time"
    assert (session.max_duration, session.break_duration, app.max_time) == (3600, 900, 1800)
    assert (range_.since, range_.till, range_.session_rule_id) == (900, 1080, session.pk)
    assert IdentifierSequence.objects.count() == 3
    assert computer_record.current_config_id is not None


def test_account_limits_monitoring_alone_does_not_create_an_empty_snapshot(
    request_client: Callable[..., Client],
    user_create: Callable[..., User],
    computer_record: Computer,
) -> None:
    account = computer_record.accounts.get()
    account.collect = False
    account.save(update_fields=("collect", "updated"))
    data = build_card_post(account)
    data["limits-collect"] = "on"
    staff_user = user_create(attributes={"is_staff": True})

    response = request_client(user=staff_user).post(reverse("core:account_limits", args=(account.pk,)), data)
    account.refresh_from_db()

    assert response.status_code == 302
    assert account.collect is True
    assert account.apply is False
    assert account.limits_id is None
    assert not Limits.objects.exists()
    assert not IdentifierSequence.objects.exists()


@pytest.mark.parametrize(
    "updates",
    [
        pytest.param({"sessions-0-max_duration": "-1"}, id="negative-duration"),
        pytest.param({"sessions-0-max_duration": "-0.001"}, id="negative-fractional-duration"),
        pytest.param({"sessions-0-break_duration": "bad"}, id="malformed-duration"),
        pytest.param({"sessions-0-max_duration": "1e1000000"}, id="excessive-duration-exponent"),
        pytest.param({"sessions-0-max_duration": "NaN"}, id="not-a-number-duration"),
        pytest.param({"ranges-0-since": "21:00"}, id="reversed-range"),
        pytest.param({"apps-0-prc_name": ""}, id="missing-recognition"),
        pytest.param({"apps-0-exe": "/usr/bin/browser", "apps-0-exe_match": ""}, id="missing-match-method"),
        pytest.param({"apps-0-prc_name": "(", "apps-0-prc_name_match": "regex"}, id="invalid-regex"),
        pytest.param({"apps-0-rule": "99"}, id="invalid-session-reference"),
    ],
)
def test_account_limits_invalid_row_preserves_every_setting_and_configuration(
    request_client: Callable[..., Client],
    user_create: Callable[..., User],
    limits_card_account: Account,
    updates: dict[str, str],
) -> None:
    account = limits_card_account
    data = build_card_post(account)
    data.update({"limits-apply": "on", "sessions-0-name": "Must not be saved", **updates})
    staff_user = user_create(attributes={"is_staff": True})
    before = read_limits_state()

    response = request_client(user=staff_user).post(reverse("core:account_limits", args=(account.pk,)), data)

    assert response.status_code == 200
    assert read_limits_state() == before


@pytest.mark.parametrize(
    "updates, removed",
    [
        pytest.param({}, ("sessions-TOTAL_FORMS",), id="missing-management"),
        pytest.param({"apps-TOTAL_FORMS": "bad"}, (), id="malformed-management"),
        pytest.param({"sessions-TOTAL_FORMS": "0", "sessions-INITIAL_FORMS": "0"}, (), id="omitted-initial-row"),
        pytest.param({}, ("ranges-0-id",), id="missing-initial-id"),
        pytest.param({"limits-limits_version": "999999"}, (), id="stale-assignment"),
        pytest.param({}, ("limits-limits_version",), id="missing-assignment-version"),
    ],
)
def test_account_limits_requires_complete_initial_rows_management_and_assignment_version(
    request_client: Callable[..., Client],
    user_create: Callable[..., User],
    limits_card_account: Account,
    updates: dict[str, str],
    removed: tuple[str, ...],
) -> None:
    account = limits_card_account
    data = build_card_post(account)
    data.update({"sessions-0-name": "Must not be saved", **updates})

    for name in removed:
        data.pop(name)

    staff_user = user_create(attributes={"is_staff": True})
    before = read_limits_state()

    response = request_client(user=staff_user).post(reverse("core:account_limits", args=(account.pk,)), data)

    assert response.status_code == 200
    assert read_limits_state() == before


@pytest.mark.parametrize("prefix", ["sessions", "ranges", "apps"])
def test_account_limits_rejects_initial_ids_outside_the_assigned_graph(
    request_client: Callable[..., Client],
    user_create: Callable[..., User],
    limits_card_account: Account,
    prefix: str,
) -> None:
    account = limits_card_account
    other_limits = Limits.objects.create(name="Other graph")
    other_session = SessionRule.objects.create(limits=other_limits, ident=101, name="Other session")
    other_range = Range.objects.create(
        limits=other_limits, session_rule=other_session, ident=102, weekday=1, since=600, till=660,
    )
    other_app = AppRule.objects.create(
        session_rule=other_session, ident=103, name="Other app", max_time=600, prc_name="other", prc_name_match="exact",
    )
    other_rows = {"sessions": other_session, "ranges": other_range, "apps": other_app}
    data = build_card_post(account)
    data[f"{prefix}-0-id"] = f"{other_rows[prefix].pk}"
    staff_user = user_create(attributes={"is_staff": True})
    before = read_limits_state()

    response = request_client(user=staff_user).post(reverse("core:account_limits", args=(account.pk,)), data)

    assert response.status_code == 200
    assert read_limits_state() == before


@pytest.mark.parametrize("second_since, valid", [("18:00", False), ("19:00", True)], ids=["overlap", "touching"])
def test_account_limits_validates_the_prospective_schedule_not_the_stored_intervals(
    request_client: Callable[..., Client],
    user_create: Callable[..., User],
    limits_card_account: Account,
    second_since: str,
    valid: bool,
) -> None:
    account = limits_card_account
    session = account.limits.session_rules.get()
    Range.objects.create(limits=account.limits, session_rule=session, ident=32, weekday=4, since=1200, till=1320)
    data = build_card_post(account)
    data.update({"ranges-0-since": "16:00", "ranges-0-till": "19:00", "ranges-1-since": second_since, "ranges-1-till": "23:00"})
    staff_user = user_create(attributes={"is_staff": True})
    before = read_limits_state()

    response = request_client(user=staff_user).post(reverse("core:account_limits", args=(account.pk,)), data)
    account.refresh_from_db()

    assert response.status_code == (302 if valid else 200)

    if valid:
        assert list(account.limits.ranges.values_list("since", "till")) == [(960, 1140), (1140, 1380)]

    else:
        assert read_limits_state() == before


@pytest.mark.parametrize(
    "updates, expected_sessions",
    [
        pytest.param({"sessions-0-DELETE": "on"}, None, id="referenced-session"),
        pytest.param({"sessions-0-DELETE": "on", "ranges-0-DELETE": "on", "apps-0-DELETE": "on"}, 0, id="delete-children"),
        pytest.param({
            "sessions-0-DELETE": "on", "sessions-TOTAL_FORMS": "2",
            "sessions-1-name": "Replacement", "sessions-1-apply": "on", "sessions-1-break_duration": "15",
            "ranges-0-rule": "1", "apps-0-rule": "1",
        }, 1, id="reassign-children"),
    ],
)
def test_account_limits_requires_children_to_be_deleted_or_reassigned_with_their_session(
    request_client: Callable[..., Client],
    user_create: Callable[..., User],
    limits_card_account: Account,
    updates: dict[str, str],
    expected_sessions: int | None,
) -> None:
    account = limits_card_account
    data = build_card_post(account)
    data.update(updates)
    staff_user = user_create(attributes={"is_staff": True})
    before = read_limits_state()

    response = request_client(user=staff_user).post(reverse("core:account_limits", args=(account.pk,)), data)

    assert response.status_code == (302 if expected_sessions is not None else 200)

    if expected_sessions is None:
        assert read_limits_state() == before

    else:
        account.refresh_from_db()
        assert account.limits.session_rules.count() == expected_sessions
        assert account.limits.ranges.count() == expected_sessions
        assert AppRule.objects.filter(session_rule__limits=account.limits).count() == expected_sessions
        assert not account.limits.session_rules.filter(ident=11).exists()
        assert not account.limits.ranges.filter(session_rule__ident=11).exists()
        assert not AppRule.objects.filter(session_rule__limits=account.limits, session_rule__ident=11).exists()


@pytest.mark.parametrize(
    "enabled, configured",
    [
        pytest.param(False, False, id="unconfigured-account"),
        pytest.param(False, True, id="enable-with-empty-schedule"),
        pytest.param(True, True, id="remove-last-active-range"),
    ],
)
@pytest.mark.parametrize("confirmed", [False, True], ids=["unconfirmed", "confirmed"])
def test_account_limits_requires_explicit_confirmation_before_blocking_all_sessions(
    request_client: Callable[..., Client],
    user_create: Callable[..., User],
    limits_card_account: Account,
    enabled: bool,
    configured: bool,
    confirmed: bool,
) -> None:
    account = limits_card_account
    account.limits.ranges.update(apply=enabled)
    account.limits = account.limits if configured else None
    account.apply = enabled
    account.collect = enabled
    account.save(update_fields=("limits", "apply", "collect", "updated"))
    data = build_card_post(account)
    data.update({
        "limits-apply": "on", "limits-collect": "", "ranges-0-apply": encode_card_value(not configured),
        "limits-confirm_empty_schedule": encode_card_value(confirmed),
    })
    staff_user = user_create(attributes={"is_staff": True})
    before = read_limits_state()

    response = request_client(user=staff_user).post(reverse("core:account_limits", args=(account.pk,)), data)
    account.refresh_from_db()

    assert response.status_code == (302 if confirmed else 200)

    if confirmed:
        assert account.apply is True
        assert account.collect is True
        assert not account.limits.ranges.filter(apply=True).exists()

    else:
        assert read_limits_state() == before
