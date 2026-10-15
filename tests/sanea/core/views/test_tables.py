"""Table values use regular text without changing column headings."""

import hashlib
import re
from collections.abc import Callable

import pytest
from django.test import Client
from django.urls import reverse
from sanelib.protocol import parse_event_packet

from sanea.core.models import AppRule, Computer, LimitsTemplate, Person, PrcExclusion, Range, User


@pytest.mark.parametrize(
    "route, expected_markup",
    [
        ("computers", ('<th scope="col" class="text-center">Учётки</th>', 'data-label="Учётки"')),
        ("accounts", ('<th scope="col">Учётка</th>',)),
    ],
)
def test_table_account_headings_are_short_without_renaming_the_navigation(
    request_client: Callable[..., Client], user_create: Callable[..., User], computer_record: Computer,
    route: str, expected_markup: tuple[str, ...],
) -> None:
    client = request_client(user=user_create(attributes={"is_staff": True}))

    response = client.get(reverse(f"core:{route}"), HTTP_ACCEPT_LANGUAGE="ru")
    content = response.content.decode()

    assert response.status_code == 200
    assert "<span>Учётные записи</span>" in content

    for markup in expected_markup:
        assert markup in content


def test_table_values_do_not_use_bold_emphasis(
    request_client: Callable[..., Client], user_create: Callable[..., User],
    computer_record: Computer, person_record: Person, limits_template_record: LimitsTemplate,
    range_record: Range, app_rule_record: AppRule, ignored_process_record: PrcExclusion,
    client_events_content: bytes,
) -> None:
    client = request_client(user=user_create(attributes={"is_staff": True}))
    account = computer_record.accounts.get()
    account.person = person_record
    account.limits = limits_template_record.current_limits
    account.save()
    packet = parse_event_packet(client_events_content, hashlib.sha256(client_events_content).hexdigest())
    account.store_event_packet(packet, len(client_events_content), None)
    pages = (
        ("people", ()),
        ("accounts", ()),
        ("computers", ()),
        ("limits", ()),
        ("statistics", ()),
        ("session_rules", (range_record.limits_id,)),
        ("ranges", (range_record.limits_id,)),
        ("app_rules", (range_record.limits_id, app_rule_record.session_rule_id)),
    )

    for route, arguments in pages:
        response = client.get(reverse(f"core:{route}", args=arguments), {"period": "7-days", "issues-period": "7-days"})
        content = response.content.decode()
        table_bodies = re.findall(r"<tbody>(.*?)</tbody>", content, re.S)

        assert response.status_code == 200, route
        assert table_bodies, route
        assert "<th scope=\"col\"" in content, route

        for body in table_bodies:
            assert "<td" in body, route
            assert not re.search(r"fw-(?:semibold|bold|bolder)|<(?:b|strong)[\s>]", body), route
