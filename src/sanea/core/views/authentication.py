"""Browser authentication views."""

from django.contrib.auth import logout
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_POST
from sitegate.decorators import redirect_signedin, signin_view


@redirect_signedin("core:dashboard")
@signin_view(
    redirect_to="core:dashboard",
    template="sanea/sitegate/signin_form.html",
    widget_attrs={"class": "form-control"},
)
def sign_in(request: HttpRequest) -> HttpResponse:
    """Render and process the sitegate sign-in flow."""
    return render(request, "sanea/sign_in.html", {"page_title": _("Sign in")})


@require_POST
def sign_out(request: HttpRequest) -> HttpResponse:
    """End the browser session and return to the sign-in page."""
    logout(request)
    return redirect("core:sign_in")
