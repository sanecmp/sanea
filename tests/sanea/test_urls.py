"""Tests for the initial browser interface routes."""

from collections.abc import Callable
from pathlib import Path

import pytest
from django.contrib.staticfiles import finders
from django.templatetags.static import static
from django.urls import resolve, reverse
from django.test import Client
from pytest_djangoapp.fixtures.settings import SettingsProxy

from sanea import urls


@pytest.mark.parametrize("secure", [False, True], ids=["http", "https"])
@pytest.mark.parametrize(
    ("asset", "content_type"),
    [
        ("sanea/css/app.css", "text/css"),
        ("sanea/js/registration-window.js", "text/javascript"),
        ("sanea/js/computers.js", "text/javascript"),
        ("sanea/js/activity-chart.js", "text/javascript"),
        ("vendor/bootstrap/bootstrap.min.css", "text/css"),
        ("vendor/htmx/htmx.min.js", "text/javascript"),
        ("sanea/favicon.svg", "image/svg+xml"),
        ("admin/css/base.css", "text/css"),
    ],
)
def test_collected_static_is_available_without_debug(
    request_client: Callable[..., Client],
    collected_static: Path,
    asset: str,
    content_type: str,
    secure: bool,
) -> None:
    response = request_client().get(static(asset), secure=secure)

    try:
        assert response.status_code == 200
        assert response.headers["Content-Type"].split(";")[0] == content_type
        assert response.headers["X-Content-Type-Options"] == "nosniff"
        assert b"".join(response.streaming_content) == (collected_static / asset).read_bytes()

    finally:
        response.close()


@pytest.mark.parametrize("asset", ["missing.css", "../sanea.env", "%2e%2e/sanea.env"])
def test_static_does_not_expose_files_outside_collection(
    request_client: Callable[..., Client],
    collected_static: Path,
    asset: str,
) -> None:
    secret = "private-test-secret"
    (collected_static.parent / "sanea.env").write_text(secret, encoding="utf-8")

    response = request_client().get(f"{static("")}{asset}")

    assert response.status_code == 404
    assert secret.encode() not in response.content


def test_development_serves_static_without_collection(
    request_client: Callable[..., Client],
    settings: SettingsProxy,
    tmp_path: Path,
) -> None:
    settings.DEBUG = True
    settings.STATIC_ROOT = tmp_path / "not-collected"
    asset = "sanea/css/app.css"
    source = finders.find(asset)
    assert source is not None

    response = request_client().get(static(asset))

    try:
        assert response.status_code == 200
        assert b"".join(response.streaming_content) == Path(source).read_bytes()
        assert not settings.STATIC_ROOT.exists()

    finally:
        response.close()


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
        ("core:statistics", {}, "/statistics/"),
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
