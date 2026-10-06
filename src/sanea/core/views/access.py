"""Access control shared by sanea browser views."""

from collections.abc import Callable
from functools import wraps
from typing import Any

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import HttpRequest, HttpResponse


def management_required(view: Callable[..., HttpResponse]) -> Callable[..., HttpResponse]:
    """Allow browser management only to staff members and superusers."""

    @login_required
    @wraps(view)
    def wrapped(request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:

        if not (request.user.is_staff or request.user.is_superuser):
            raise PermissionDenied

        return view(request, *args, **kwargs)

    return wrapped
