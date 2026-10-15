"""Navigation back from nested settings pages."""

from collections.abc import Callable

import pytest
from django.test import Client
from django.urls import reverse
from django.utils.html import escape

from sanea.core.models import Computer, Limits, Range, SessionRule, User


@pytest.mark.parametrize(
    "route, account_name",
    [
        ("ranges", "Synthetic account"),
        ("session_rules", "Synthetic account"),
        ("app_rules", "Synthetic account"),
        ("account_limits", "Synthetic account"),
        ("account_limits", ""),
        ("account_rule_delete", "Synthetic account"),
    ],
)
def test_nested_pages_show_parent_links_in_breadcrumbs(
    request_client: Callable[..., Client], user_create: Callable[..., User], computer_record: Computer,
    limits_record: Limits, session_rule_record: SessionRule, range_record: Range, route: str, account_name: str,
) -> None:
    account = computer_record.accounts.get()
    account.limits = limits_record
    account.name = account_name
    account.save(update_fields=("limits", "name", "updated"))
    scope = {"limits_pk": limits_record.pk}
    pages = {
        "ranges": (scope, "Schedule ranges", [reverse("core:limits")]),
        "session_rules": (scope, "Session rules", [reverse("core:limits")]),
        "app_rules": (
            {**scope, "rule_pk": session_rule_record.pk}, "Application rules",
            [reverse("core:limits"), reverse("core:session_rules", kwargs=scope)],
        ),
        "account_limits": ({"account_pk": account.pk}, escape(account.name or account.login), [reverse("core:accounts")]),
        "account_rule_delete": (
            {"account_pk": account.pk, "kind": "ranges", "rule_pk": range_record.pk}, "Remove restriction",
            [reverse("core:accounts"), reverse("core:account_limits", args=(account.pk,))],
        ),
    }
    kwargs, title, parent_urls = pages[route]

    response = request_client(user=user_create(attributes={"is_staff": True})).get(reverse(f"core:{route}", kwargs=kwargs))
    content = response.content.decode()

    assert response.status_code == 200
    assert "<nav aria-label=\"Breadcrumbs\">" in content
    assert f"<li class=\"breadcrumb-item active\" aria-current=\"page\">{title}</li>" in content

    for url in parent_urls:
        assert f"class=\"link-secondary\" href=\"{url}\"" in content
