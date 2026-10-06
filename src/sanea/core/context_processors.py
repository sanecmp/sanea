"""Template context shared by the browser interface."""

from django.http import HttpRequest

from .. import __version__


def application(request: HttpRequest) -> dict[str, str]:
    """Expose application metadata to all templates."""
    return {"application_version": __version__}
