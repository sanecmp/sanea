"""Tests for local PKI initialization."""

import stat
from datetime import timedelta
from pathlib import Path

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import ExtendedKeyUsageOID

from sanea.exceptions import PkiError, SaneaException
from sanea.utils.pki import PkiStore


def test_creates_complete_pki_once_and_secures_private_material(
    tmp_path: Path,
) -> None:
    store = PkiStore(tmp_path / "state" / "pki")

    store.ensure()
    original = {path.name: path.read_bytes() for path in store.paths}
    store.directory.chmod(0o777)
    store.ca_private_key_path.chmod(0o666)
    store.server_private_key_path.chmod(0o666)
    store.ensure()

    ca_certificate = x509.load_pem_x509_certificate(
        store.ca_certificate_path.read_bytes()
    )
    server_certificate = x509.load_pem_x509_certificate(
        store.server_certificate_path.read_bytes()
    )
    ca_key = serialization.load_pem_private_key(
        store.ca_private_key_path.read_bytes(),
        password=None,
    )
    server_key = serialization.load_pem_private_key(
        store.server_private_key_path.read_bytes(),
        password=None,
    )

    assert original == {path.name: path.read_bytes() for path in store.paths}
    assert isinstance(ca_key.curve, ec.SECP256R1)
    assert isinstance(server_key.curve, ec.SECP256R1)
    assert ca_certificate.extensions.get_extension_for_class(
        x509.BasicConstraints
    ).value.ca
    server_usages = server_certificate.extensions.get_extension_for_class(
        x509.ExtendedKeyUsage
    ).value
    ca_lifetime = (
        ca_certificate.not_valid_after_utc
        - ca_certificate.not_valid_before_utc
    )
    server_lifetime = (
        server_certificate.not_valid_after_utc
        - server_certificate.not_valid_before_utc
    )
    assert ExtendedKeyUsageOID.SERVER_AUTH in server_usages
    assert ca_lifetime >= timedelta(days=20 * 365)
    assert server_lifetime >= timedelta(days=10 * 365)
    assert stat.S_IMODE(store.directory.stat().st_mode) == 0o700
    assert stat.S_IMODE(store.ca_private_key_path.stat().st_mode) == 0o600
    assert stat.S_IMODE(store.server_private_key_path.stat().st_mode) == 0o600


def test_refuses_to_replace_incomplete_existing_pki(tmp_path: Path) -> None:
    store = PkiStore(tmp_path / "pki")
    store.directory.mkdir()
    store.ca_certificate_path.write_text("not a certificate")

    with pytest.raises(PkiError, match="Incomplete PKI"):
        store.ensure()

    assert store.ca_certificate_path.read_text() == "not a certificate"
    assert issubclass(PkiError, SaneaException)
