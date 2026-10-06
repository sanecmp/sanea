"""WSGI application exported for the embedded Cheroot server."""

import os

from django.core.wsgi import get_wsgi_application


os.environ.setdefault("DJANGO_SETTINGS_MODULE", "sanea.settings")

application = get_wsgi_application()
