"""Common lifecycle for authenticated, progressively enhanced views."""

from abc import ABC, abstractmethod
from collections.abc import Callable

from django.http import HttpRequest, HttpResponse
from siteajax.decorators import ajax_dispatch

from .access import management_required


class ManagedView(ABC):
    """Build one protected Django view with optional siteajax handlers."""

    def as_view(self) -> Callable[..., HttpResponse]:
        """Decorate this stateless view for access control and AJAX dispatch."""
        view = self.dispatch
        handlers = self.get_ajax_handlers()

        if handlers:
            view = ajax_dispatch(handlers)(view)

        return management_required(view)

    def get_ajax_handlers(self) -> dict[str, Callable[..., HttpResponse]]:
        """Return siteajax handlers keyed by trigger pattern."""
        return {}

    @abstractmethod
    def dispatch(self, request: HttpRequest, **kwargs: object) -> HttpResponse:
        """Handle a regular non-siteajax request."""
