"""Tests for browser authentication."""

from collections.abc import Callable

from django.urls import reverse
from django.test import Client

from sanea.core.models import User


def test_sign_in_uses_sitegate_form(request_client: Callable[..., Client]) -> None:
    response = request_client().get(reverse("core:sign_in"))
    content = response.content.decode()

    assert response.status_code == 200
    assert "name=\"signin_flow\"" in content
    assert "value=\"ModernSignin\"" in content
    assert "name=\"username\"" in content
    assert "name=\"password\"" in content
    assert "href=\"/static/sanea/favicon.svg\"" in content
    assert reverse("admin:index") not in content


def test_sign_in_uses_browser_language(request_client: Callable[..., Client]) -> None:
    russian = request_client().get(
        reverse("core:sign_in"),
        HTTP_ACCEPT_LANGUAGE="ru-RU,ru;q=0.9,en;q=0.8",
    )
    english = request_client().get(
        reverse("core:sign_in"),
        HTTP_ACCEPT_LANGUAGE="en-US,en;q=0.9,ru;q=0.8",
    )

    assert "<html lang=\"ru\">" in russian.content.decode()
    assert "Войти" in russian.content.decode()
    assert "<html lang=\"en\">" in english.content.decode()
    assert "Sign in" in english.content.decode()


def test_sitegate_signs_management_user_in(request_client: Callable[..., Client], user_create: Callable[..., User]) -> None:
    user = user_create(attributes={"is_staff": True})
    client = request_client()

    response = client.post(
        reverse("core:sign_in"),
        {
            "username": user.username,
            "password": user.password_plain,
            "signin_flow": "ModernSignin",
        },
    )

    assert response.status_code == 302
    assert response.url == reverse("core:dashboard")
    assert client.get(reverse("core:dashboard")).status_code == 200


def test_sign_out_requires_post(request_client: Callable[..., Client], user_create: Callable[..., User]) -> None:
    user = user_create(attributes={"is_staff": True})
    client = request_client(user=user)

    assert client.get(reverse("core:sign_out")).status_code == 405

    response = client.post(reverse("core:sign_out"))

    assert response.status_code == 302
    assert response.url == reverse("core:sign_in")
    assert client.get(reverse("core:dashboard")).url.startswith(reverse("core:sign_in"))
