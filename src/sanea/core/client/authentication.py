"""Identity transferred by the TLS-serving WSGI adapter."""

import re

from django.http import HttpRequest

from ..models import Computer


VERIFIED_CERTIFICATE_FINGERPRINT_META = (
    "sanea.verified_client_certificate_fingerprint"
)
_FINGERPRINT = re.compile(r"[0-9a-f]{64}")


def computer_from_verified_certificate(request: HttpRequest) -> Computer | None:
    """Resolve a computer from the private verified-certificate WSGI value."""
    fingerprint = request.META.get(VERIFIED_CERTIFICATE_FINGERPRINT_META)

    if not isinstance(fingerprint, str) or _FINGERPRINT.fullmatch(fingerprint) is None:
        return None

    return Computer.objects.filter(certificate_fingerprint=fingerprint).first()
