"""Browser authentication views."""

from copy import copy

from django.contrib.auth import logout
from django.forms import BaseForm
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_POST
from sitegate.decorators import redirect_signedin, signin_view
from sitegate.signin_flows.modern import ModernSignin as SitegateModernSignin


class ModernSignin(SitegateModernSignin):
    """Keep sitegate's template choice local to its sign-in form."""

    def init_form(
        self, form_data: dict | None, widget_attrs: dict | None = None, template: str | None = None,
    ) -> BaseForm:
        """Isolate the renderer before sitegate changes its form template."""
        form = super().init_form(form_data, widget_attrs=widget_attrs, template=template)
        form.renderer = copy(form.renderer)
        return form


@redirect_signedin("core:dashboard")
@signin_view(
    flow=ModernSignin,
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
