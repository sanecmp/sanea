"""Independent, confirmed deletion of saved account restrictions."""

from collections.abc import Callable

import pytest
from django.core.exceptions import ValidationError
from django.test import Client
from django.urls import reverse

from sanea.core.models import (
    Account, AppRule, Computer, ComputerConfig, IdentifierSequence,
    Limits, LimitsTemplate, Range, SessionRule, User,
)


@pytest.fixture
def deletion_account(computer_record: Computer, range_record: Range, app_rule_record: AppRule) -> Account:
    account = computer_record.accounts.get()
    account.limits = range_record.limits
    account.save(update_fields=("limits", "updated"))
    return account


@pytest.fixture
def deletion_client(request_client: Callable[..., Client], user_create: Callable[..., User]) -> Client:
    return request_client(user=user_create(attributes={"is_staff": True}))


def read_deletion_state() -> dict[str, object]:
    models = (Account, Limits, SessionRule, Range, AppRule, LimitsTemplate, Computer, ComputerConfig, IdentifierSequence)
    return {model.__name__: tuple(model.objects.order_by("pk").values()) for model in models}


@pytest.mark.parametrize("method", ["get", "post"])
def test_account_rule_delete_requires_management_user(
    request_client: Callable[..., Client], user_create: Callable[..., User], deletion_account: Account, method: str,
) -> None:
    rule = deletion_account.limits.session_rules.get()
    url = reverse("core:account_rule_delete", args=(deletion_account.pk, "sessions", rule.pk))
    regular_user = user_create()
    before = read_deletion_state()

    anonymous = getattr(request_client(), method)(url)
    regular = getattr(request_client(user=regular_user), method)(url)

    assert anonymous.status_code == 302
    assert anonymous.url.startswith(reverse("core:sign_in"))
    assert regular.status_code == 403
    assert read_deletion_state() == before


@pytest.mark.parametrize("kind", ["sessions", "ranges", "apps"])
@pytest.mark.parametrize("method, include_version", [("get", False), ("post", False), ("post", True)])
def test_account_rule_delete_preview_never_writes_and_renders_a_confirmable_form(
    deletion_client: Client, deletion_account: Account, kind: str, method: str, include_version: bool,
) -> None:
    account = deletion_account
    rule = account.get_limits_rules(kind).get()
    url = reverse("core:account_rule_delete", args=(account.pk, kind, rule.pk))
    data = {"limits_version": f"{account.limits_id}", "confirmed": "", "confirm_empty_schedule": "on"} if include_version else {}
    before = read_deletion_state()

    response = getattr(deletion_client, method)(url, data)
    content = response.content.decode()

    assert response.status_code == 200
    assert f"action=\"{url}\"" in content
    assert f"name=\"limits_version\" value=\"{account.limits_id}\"" in content
    assert "name=\"confirmed\" value=\"True\"" in content
    assert "Other unsaved changes will be discarded." in content
    assert "type=\"checkbox\" name=\"confirm_empty_schedule\"" not in content
    assert read_deletion_state() == before


@pytest.mark.parametrize("kind, expected_counts", [("sessions", (1, 1, 1)), ("ranges", (2, 1, 2)), ("apps", (2, 2, 1))])
def test_account_rule_delete_is_immediate_scoped_preserves_identities_and_ignores_editor_drafts(
    deletion_client: Client, deletion_account: Account, kind: str, expected_counts: tuple[int, int, int],
) -> None:
    account = deletion_account
    source = account.limits
    original_rule = account.get_limits_rules(kind).get()
    remaining_session = SessionRule.objects.create(limits=source, ident=12, name="Kept preset")
    Range.objects.create(limits=source, session_rule=remaining_session, ident=32, weekday=5, since=600, till=660)
    AppRule.objects.create(
        session_rule=remaining_session, ident=22, name="Kept application", max_time=600,
        prc_name="kept", prc_name_match="exact",
    )
    template = LimitsTemplate.objects.create(name="Shared template", current_limits=source)
    sibling = Account.objects.create(computer=account.computer, limits=source, uid=1002, login="sibling", name="Sibling")
    original_graph = source.build_client_config()
    identifiers = tuple(IdentifierSequence.objects.order_by("pk").values())
    url = reverse("core:account_rule_delete", args=(account.pk, kind, original_rule.pk))

    response = deletion_client.post(url, {
        "limits_version": f"{source.pk}", "confirmed": "on", "limits-collect": "", "limits-apply": "on",
        "sessions-0-name": "Must not be saved", "ranges-0-since": "invalid", "apps-0-name": "Draft",
    })
    account.refresh_from_db()
    template.refresh_from_db()
    sibling.refresh_from_db()

    assert response.status_code == 302
    assert response.url == f"{reverse('core:account_limits', args=(account.pk,))}?removed=1"
    assert account.limits_id != source.pk
    assert account.collect is True
    assert account.apply is False
    assert template.current_limits_id == sibling.limits_id == source.pk
    assert source.build_client_config() == original_graph
    assert tuple(account.get_limits_rules(name).count() for name in ("sessions", "ranges", "apps")) == expected_counts
    assert not account.get_limits_rules(kind).filter(ident=original_rule.ident).exists()
    assert account.limits.session_rules.get(ident=12).name == "Kept preset"
    assert account.limits.ranges.get(ident=32).session_rule.ident == 12
    assert account.get_limits_rules("apps").get(ident=22).name == "Kept application"
    assert tuple(IdentifierSequence.objects.order_by("pk").values()) == identifiers
    assert ComputerConfig.objects.count() == 1
    assert "Restriction removed." in deletion_client.get(response.url).content.decode()


@pytest.mark.parametrize("kind", ["sessions", "ranges", "apps", "unknown"])
def test_account_rule_delete_rejects_foreign_rules_and_unknown_kinds_without_writes(
    deletion_client: Client, deletion_account: Account, kind: str,
) -> None:
    other = Limits.objects.create(name="Foreign snapshot")
    session = SessionRule.objects.create(limits=other, ident=101, name="Foreign preset")
    interval = Range.objects.create(limits=other, session_rule=session, ident=102, weekday=1, since=600, till=660)
    application = AppRule.objects.create(
        session_rule=session, ident=103, name="Foreign application", max_time=600, prc_name="other", prc_name_match="exact",
    )
    rules = {"sessions": session, "ranges": interval, "apps": application, "unknown": session}
    before = read_deletion_state()

    response = deletion_client.post(
        reverse("core:account_rule_delete", args=(deletion_account.pk, kind, rules[kind].pk)),
        {"limits_version": f"{deletion_account.limits_id}", "confirmed": "on"},
    )

    assert response.status_code == 404
    assert read_deletion_state() == before


@pytest.mark.parametrize("version", [None, "not-a-number"])
def test_account_rule_delete_final_confirmation_requires_a_valid_snapshot_version(
    deletion_client: Client, deletion_account: Account, version: str | None,
) -> None:
    account = deletion_account
    data = {"confirmed": "on"}

    if version is not None:
        data["limits_version"] = version

    before = read_deletion_state()
    response = deletion_client.post(
        reverse("core:account_rule_delete", args=(account.pk, "sessions", account.limits.session_rules.get().pk)), data,
    )

    assert response.status_code == 200
    assert "alert alert-danger" in response.content.decode()
    assert "name=\"confirmed\" value=\"on\"" in response.content.decode()
    assert read_deletion_state() == before


@pytest.mark.parametrize("confirmed", [False, True])
def test_account_rule_delete_rejects_stale_versions_before_resolving_old_rule_ids(
    deletion_client: Client, deletion_account: Account, confirmed: bool,
) -> None:
    account = deletion_account
    version = account.limits_id
    rule = account.get_limits_rules("apps").get()
    url = reverse("core:account_rule_delete", args=(account.pk, "apps", rule.pk))
    data = {"limits_version": f"{version}", "confirmed": "on"}
    assert deletion_client.post(url, data).status_code == 302
    before = read_deletion_state()

    response = deletion_client.post(url, {**data, "confirmed": "on" if confirmed else ""})

    assert response.status_code == 409
    assert "The rules changed. Reload the card before removing a rule." in response.content.decode()
    assert read_deletion_state() == before

    with pytest.raises(ValidationError, match="The rules changed"):
        account.remove_limits_rule("apps", rule.pk, limits_version=version)

    assert read_deletion_state() == before


@pytest.mark.parametrize("kind", ["sessions", "ranges"])
def test_account_rule_delete_requires_separate_confirmation_for_the_last_active_interval(
    deletion_client: Client, deletion_account: Account, kind: str,
) -> None:
    account = deletion_account
    account.apply = True
    account.save(update_fields=("apply", "updated"))
    rule = account.get_limits_rules(kind).get()
    url = reverse("core:account_rule_delete", args=(account.pk, kind, rule.pk))
    data = {"limits_version": f"{account.limits_id}", "confirmed": "on"}
    before = read_deletion_state()

    unconfirmed = deletion_client.post(url, data)

    assert unconfirmed.status_code == 200
    assert "Explicitly confirm blocking all sessions" in unconfirmed.content.decode()
    assert "type=\"checkbox\" name=\"confirm_empty_schedule\"" in unconfirmed.content.decode()
    assert read_deletion_state() == before

    confirmed = deletion_client.post(url, {**data, "confirm_empty_schedule": "on"})
    account.refresh_from_db()

    assert confirmed.status_code == 302
    assert account.apply is True
    assert not account.limits.ranges.filter(apply=True).exists()


@pytest.mark.parametrize(
    "kind, active_range, remaining_range",
    [("sessions", False, False), ("ranges", False, False), ("ranges", True, True), ("apps", True, False)],
)
def test_account_rule_delete_does_not_require_blocking_confirmation_without_a_newly_empty_schedule(
    deletion_client: Client, deletion_account: Account, kind: str, active_range: bool, remaining_range: bool,
) -> None:
    account = deletion_account
    account.apply = True
    account.save(update_fields=("apply", "updated"))
    account.limits.ranges.update(apply=active_range)
    rule = account.get_limits_rules(kind).get()

    if remaining_range:
        Range.objects.create(limits=account.limits, session_rule=rule.session_rule, ident=32, weekday=5, since=600, till=660)

    response = deletion_client.post(
        reverse("core:account_rule_delete", args=(account.pk, kind, rule.pk)),
        {"limits_version": f"{account.limits_id}", "confirmed": "on"},
    )

    assert response.status_code == 302


@pytest.mark.parametrize("kind", ["sessions", "ranges", "apps"])
def test_account_rule_delete_rolls_back_graph_and_configuration_on_materialization_failure(
    deletion_client: Client, deletion_account: Account, monkeypatch: pytest.MonkeyPatch, kind: str,
) -> None:
    account = deletion_account
    rule = account.get_limits_rules(kind).get()
    materialize = Computer.materialize_config

    def fail_materialization(computer: Computer) -> None:
        materialize(computer)
        raise RuntimeError("Synthetic materialization failure")

    monkeypatch.setattr(Computer, "materialize_config", fail_materialization)
    before = read_deletion_state()

    with pytest.raises(RuntimeError, match="Synthetic materialization failure"):
        deletion_client.post(
            reverse("core:account_rule_delete", args=(account.pk, kind, rule.pk)),
            {"limits_version": f"{account.limits_id}", "confirmed": "on"},
        )

    assert read_deletion_state() == before


def test_account_rule_delete_enforces_csrf_and_only_accepts_get_or_post(
    deletion_account: Account, user_create: Callable[..., User],
) -> None:
    account = deletion_account
    client = Client(enforce_csrf_checks=True)
    client.force_login(user_create(attributes={"is_staff": True}))
    url = reverse("core:account_rule_delete", args=(account.pk, "apps", account.get_limits_rules("apps").get().pk))
    before = read_deletion_state()

    missing_csrf = client.post(url, {"limits_version": f"{account.limits_id}", "confirmed": "on"})
    unsupported = client.put(url)

    assert missing_csrf.status_code == 403
    assert unsupported.status_code == 403
    assert read_deletion_state() == before

    client.get(url)
    token = client.cookies["csrftoken"].value
    unsupported_with_csrf = client.put(url, HTTP_X_CSRFTOKEN=token)
    confirmed = client.post(
        url, {"limits_version": f"{account.limits_id}", "confirmed": "on"}, HTTP_X_CSRFTOKEN=token,
    )

    assert unsupported_with_csrf.status_code == 405
    assert confirmed.status_code == 302
