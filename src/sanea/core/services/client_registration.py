"""Initial sanex registration and client certificate issuance."""

import hashlib
from dataclasses import dataclass

from cryptography import x509
from cryptography.exceptions import UnsupportedAlgorithm
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from django.conf import settings
from django.db import transaction
from sanelib.protocol import RegistrationConfirmRequest, RegistrationRequest

from ...exceptions import ClientAccessError, ClientRequestError
from ...utils.pki import PkiStore
from ..models import Computer, ComputerConfig, ComputerStatus
from .registration_window import RegistrationWindow


@dataclass(frozen=True)
class ClientRegistrationResult:
    """Certificate material returned for an accepted or repeated CSR."""

    computer: Computer
    ca: str
    certificate: str


@dataclass(frozen=True)
class ClientRegistrationConfirmResult:
    """Initial configuration returned after authenticated confirmation."""

    config: ComputerConfig


def register_client(
    request: RegistrationRequest,
    window: RegistrationWindow,
) -> ClientRegistrationResult:
    """Validate a CSR, claim the window and persist a pending computer."""
    public_key, public_key_fingerprint = _validate_csr(request.csr)
    pki = PkiStore(settings.PKI_DIR)

    with transaction.atomic():
        existing = (
            Computer.objects.select_for_update()
            .filter(public_key_fingerprint=public_key_fingerprint)
            .first()
        )

        if existing is not None:
            return _repeat_registration(existing, pki)

        if not window.claim(request.code):
            raise ClientAccessError("Registration window is closed or code is invalid")

        bundle = pki.issue_client_certificate(public_key)
        certificate = bundle.certificate
        computer = Computer.create_pending_registration(
            hostname=request.hostname,
            public_key_fingerprint=public_key_fingerprint,
            certificate_fingerprint=bundle.fingerprint,
            client_certificate=certificate,
        )

    return ClientRegistrationResult(
        computer=computer,
        ca=bundle.ca,
        certificate=certificate,
    )


@transaction.atomic
def confirm_client_registration(
    computer: Computer,
    request: RegistrationConfirmRequest,
    remote_ip: str | None,
) -> ClientRegistrationConfirmResult:
    """Apply initial client state and idempotently complete registration."""
    locked_computer = Computer.objects.select_for_update().get(pk=computer.pk)
    locked_computer.ensure_registration_confirmation_allowed()

    locked_computer.update_contact(
        request.version,
        remote_ip,
        status=ComputerStatus.ALLOWED,
    )
    locked_computer.apply_account_snapshot(request.accounts)
    config = locked_computer.materialize_config()
    return ClientRegistrationConfirmResult(config=config)


def _validate_csr(
    csr_pem: str,
) -> tuple[ec.EllipticCurvePublicKey, str]:
    try:
        csr = x509.load_pem_x509_csr(csr_pem.encode())

        if not csr.is_signature_valid:
            raise ClientRequestError("CSR signature is invalid")

        public_key = csr.public_key()

    except ClientRequestError:
        raise

    except (TypeError, UnsupportedAlgorithm, ValueError) as error:
        raise ClientRequestError("CSR is invalid") from error

    if not isinstance(public_key, ec.EllipticCurvePublicKey) or not isinstance(
        public_key.curve,
        ec.SECP256R1,
    ):
        raise ClientRequestError("CSR must use an ECDSA P-256 key")

    encoded_public_key = public_key.public_bytes(
        serialization.Encoding.DER,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return public_key, hashlib.sha256(encoded_public_key).hexdigest()


def _repeat_registration(
    computer: Computer,
    pki: PkiStore,
) -> ClientRegistrationResult:
    certificate = computer.client_certificate

    if computer.status != ComputerStatus.PENDING or not certificate:
        raise ClientAccessError("Computer is already registered")

    return ClientRegistrationResult(
        computer=computer,
        ca=pki.read_ca_certificate(),
        certificate=certificate,
    )
