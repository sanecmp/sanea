"""Tests for initial sanex registration and certificate issuance."""

import base64
import hashlib
import json
from importlib import import_module
from pathlib import Path
from typing import Any
from collections.abc import Callable

from django.urls import reverse
import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID
from django.http import HttpResponse
from django.test import Client
from pytest_djangoapp.fixtures.settings import SettingsProxy

from sanea.core.models import Computer, ComputerStatus
from sanea.core.services.registration_window import RegistrationWindow


REGISTER_URL = reverse("core:client_register")


def _csr_pem(private_key: ec.EllipticCurvePrivateKey | rsa.RSAPrivateKey) -> str:
    return (
        x509.CertificateSigningRequestBuilder()
        .subject_name(
            x509.Name(
                [x509.NameAttribute(NameOID.COMMON_NAME, "ignored CSR subject")]
            )
        )
        .add_extension(
            x509.SubjectAlternativeName([x509.DNSName("ignored.example")]),
            critical=False,
        )
        .sign(private_key, hashes.SHA256())
        .public_bytes(serialization.Encoding.PEM)
        .decode()
    )


def _corrupt_csr_signature(csr_pem: str) -> str:
    csr = x509.load_pem_x509_csr(csr_pem.encode())
    encoded = bytearray(csr.public_bytes(serialization.Encoding.DER))
    encoded[-1] ^= 1
    payload = base64.encodebytes(bytes(encoded)).decode()
    return (
        "-----BEGIN CERTIFICATE REQUEST-----\n"
        f"{payload}"
        "-----END CERTIFICATE REQUEST-----\n"
    )


def _registration_request(
    client: Client,
    payload: dict[str, Any],
    *,
    secure: bool = True,
) -> HttpResponse:
    return client.post(
        REGISTER_URL,
        json.dumps(payload),
        content_type="application/json",
        secure=secure,
    )


@pytest.fixture
def registration_endpoint(monkeypatch: pytest.MonkeyPatch) -> RegistrationWindow:
    """Install an isolated registration window in the endpoint module."""
    window = RegistrationWindow()
    client_module = import_module("sanea.core.views.client")
    monkeypatch.setattr(client_module, "registration_window", window)
    return window


def test_registration_requires_https_without_consuming_window(
    request_client: Callable[..., Client],
    client_registration_payload: dict[str, Any],
    registration_endpoint: RegistrationWindow,
) -> None:
    key = ec.generate_private_key(ec.SECP256R1())
    code = registration_endpoint.open().code
    payload = {
        **client_registration_payload,
        "code": code,
        "csr": _csr_pem(key),
    }

    response = _registration_request(request_client(), payload, secure=False)

    assert response.status_code == 403
    assert registration_endpoint.get_snapshot().code == code
    assert Computer.objects.count() == 0


@pytest.mark.parametrize("invalid_csr", ["not a CSR", None])
def test_invalid_request_does_not_consume_window(
    request_client: Callable[..., Client],
    client_registration_payload: dict[str, Any],
    registration_endpoint: RegistrationWindow,
    invalid_csr: object,
) -> None:
    code = registration_endpoint.open().code
    payload = {
        **client_registration_payload,
        "code": code,
        "csr": invalid_csr,
    }

    response = _registration_request(request_client(), payload)

    assert response.status_code == 422
    assert registration_endpoint.get_snapshot().code == code
    assert Computer.objects.count() == 0


def test_invalid_csr_signature_does_not_consume_window(
    request_client: Callable[..., Client],
    client_registration_payload: dict[str, Any],
    registration_endpoint: RegistrationWindow,
) -> None:
    code = registration_endpoint.open().code
    key = ec.generate_private_key(ec.SECP256R1())
    payload = {
        **client_registration_payload,
        "code": code,
        "csr": _corrupt_csr_signature(_csr_pem(key)),
    }

    response = _registration_request(request_client(), payload)

    assert response.status_code == 422
    assert registration_endpoint.get_snapshot().code == code
    assert Computer.objects.count() == 0


def test_unsupported_csr_key_does_not_consume_window(
    request_client: Callable[..., Client],
    client_registration_payload: dict[str, Any],
    registration_endpoint: RegistrationWindow,
) -> None:
    code = registration_endpoint.open().code
    payload = {
        **client_registration_payload,
        "code": code,
        "csr": _csr_pem(rsa.generate_private_key(public_exponent=65537, key_size=2048)),
    }

    response = _registration_request(request_client(), payload)

    assert response.status_code == 422
    assert registration_endpoint.get_snapshot().code == code
    assert Computer.objects.count() == 0


def test_wrong_code_does_not_consume_window(
    request_client: Callable[..., Client],
    client_registration_payload: dict[str, Any],
    registration_endpoint: RegistrationWindow,
) -> None:
    key = ec.generate_private_key(ec.SECP256R1())
    code = registration_endpoint.open().code
    payload = {
        **client_registration_payload,
        "code": "ABCD-EFGH",
        "csr": _csr_pem(key),
    }

    if payload["code"] == code:
        payload["code"] = "2345-6789"

    response = _registration_request(request_client(), payload)

    assert response.status_code == 403
    assert registration_endpoint.get_snapshot().code == code
    assert Computer.objects.count() == 0


def test_issues_client_certificate_and_repeats_same_response(
    request_client: Callable[..., Client],
    client_registration_payload: dict[str, Any],
    registration_endpoint: RegistrationWindow,
    settings: SettingsProxy,
    tmp_path: Path,
) -> None:
    key = ec.generate_private_key(ec.SECP256R1())
    code = registration_endpoint.open().code
    csr_pem = _csr_pem(key)
    payload = {
        **client_registration_payload,
        "code": code,
        "csr": csr_pem,
    }

    with settings(PKI_DIR=tmp_path / "pki"):
        response = _registration_request(request_client(), payload)
        repeated = _registration_request(request_client(), payload)

    body = response.json()
    certificate = x509.load_pem_x509_certificate(body["certificate"].encode())
    ca_certificate = x509.load_pem_x509_certificate(body["ca"].encode())
    computer = Computer.objects.get()
    public_key_bytes = key.public_key().public_bytes(
        serialization.Encoding.DER,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )

    ca_certificate.public_key().verify(
        certificate.signature,
        certificate.tbs_certificate_bytes,
        ec.ECDSA(certificate.signature_hash_algorithm),
    )
    assert response.status_code == 201
    assert repeated.status_code == 201
    assert repeated.json() == body
    assert Computer.objects.count() == 1
    assert computer.hostname == client_registration_payload["hostname"]
    assert computer.status == ComputerStatus.PENDING
    assert computer.public_key_fingerprint == hashlib.sha256(
        public_key_bytes
    ).hexdigest()
    assert computer.certificate_fingerprint == certificate.fingerprint(
        hashes.SHA256()
    ).hex()
    assert computer.client_certificate == body["certificate"]
    assert certificate.public_key().public_bytes(
        serialization.Encoding.DER,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    ) == public_key_bytes
    assert certificate.subject.get_attributes_for_oid(NameOID.COMMON_NAME)[0].value == (
        "sanex client"
    )
    extended_key_usage = certificate.extensions.get_extension_for_class(
        x509.ExtendedKeyUsage
    ).value
    assert ExtendedKeyUsageOID.CLIENT_AUTH in extended_key_usage

    with pytest.raises(x509.ExtensionNotFound):
        certificate.extensions.get_extension_for_class(x509.SubjectAlternativeName)

    assert registration_endpoint.get_snapshot() is None
