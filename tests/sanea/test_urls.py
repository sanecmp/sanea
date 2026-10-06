"""Tests for the initial browser interface routes."""

from collections.abc import Callable

import pytest
from django.urls import resolve, reverse
from django.test import Client
from pytest_djangoapp.fixtures.settings import SettingsProxy

from sanea import urls


def test_admin_login_is_available(request_client: Callable[..., Client], settings: SettingsProxy) -> None:

    with settings(ALLOWED_HOSTS=[*settings.ALLOWED_HOSTS, "testserver"]):
        response = request_client().get(reverse("admin:login"))

    assert response.status_code == 200


def test_sitetree_uses_dynamic_trees_only(settings: SettingsProxy) -> None:
    assert settings.SITETREE_DYNAMIC_ONLY is True


@pytest.mark.parametrize(
    ("view_name", "kwargs", "expected"),
    [
        ("core:dashboard", {}, "/"),
        ("core:people", {}, "/people/"),
        ("core:computers", {}, "/computers/"),
        ("core:accounts", {}, "/accounts/"),
        ("core:limits", {}, "/limits/"),
        ("core:ranges", {"limits_pk": 17}, "/limits/17/ranges/"),
        ("core:session_rules", {"limits_pk": 17}, "/limits/17/session-rules/"),
        (
            "core:app_rules",
            {"limits_pk": 17, "rule_pk": 23},
            "/limits/17/session-rules/23/app-rules/",
        ),
        ("core:issues", {}, "/issues/"),
        ("core:ignored_processes", {}, "/settings/ignored-processes/"),
        ("core:sign_in", {}, "/signin/"),
        ("core:sign_out", {}, "/signout/"),
        ("core:client_log", {}, "/client/log"),
        ("core:client_sync", {}, "/client/sync"),
        ("core:client_register", {}, "/client/register"),
        ("core:client_register_confirm", {}, "/client/register/confirm"),
        (
            "core:client_events",
            {"uid": 1001, "sha256": "a" * 64},
            f"/client/events/1001/{"a" * 64}",
        ),
        ("admin:login", {}, "/admin/login/"),
    ],
)
def test_named_routes_keep_paths_and_captured_parameters(
    view_name: str,
    kwargs: dict[str, int | str],
    expected: str,
) -> None:
    path = reverse(view_name, kwargs=kwargs)
    match = resolve(path)

    assert urls.app_name == "sanea"
    assert path == expected
    assert match.view_name == view_name
    assert match.kwargs == kwargs
