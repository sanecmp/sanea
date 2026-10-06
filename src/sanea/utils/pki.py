"""Local certificate authority and server identity management."""

import shutil
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from cryptography import x509
from cryptography.exceptions import InvalidSignature, UnsupportedAlgorithm
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID
from cryptography.hazmat.primitives.asymmetric.types import PrivateKeyTypes

from ..exceptions import PkiError


@dataclass(frozen=True)
class ClientCertificateBundle:
    """PEM material and identity of one issued sanex client certificate."""

    ca: str
    certificate: str
    fingerprint: str


class PkiStore:
    """Create and validate the persistent sanea certificate store."""

    _CA_LIFETIME = timedelta(days=20 * 365)
    _SERVER_LIFETIME = timedelta(days=10 * 365)
    _CLIENT_LIFETIME = timedelta(days=10 * 365)

    def __init__(self, directory: Path) -> None:
        self.directory = directory

    @property
    def ca_certificate_path(self) -> Path:
        return self.directory / "ca.crt"

    @property
    def ca_private_key_path(self) -> Path:
        return self.directory / "ca.key"

    @property
    def server_certificate_path(self) -> Path:
        return self.directory / "server.crt"

    @property
    def server_private_key_path(self) -> Path:
        return self.directory / "server.key"

    @property
    def paths(self) -> tuple[Path, ...]:
        return (
            self.ca_certificate_path,
            self.ca_private_key_path,
            self.server_certificate_path,
            self.server_private_key_path,
        )

    def ensure(self) -> None:
        """Create a missing store atomically or validate the existing store."""

        if self.directory.exists():

            if self.directory.is_symlink():
                raise PkiError(
                    f"PKI directory '{self.directory}' must not be a symlink"
                )

            self._validate_complete_store()
            self._tighten_permissions()
            return

        try:
            self.directory.parent.mkdir(parents=True, exist_ok=True)
            staging = Path(
                tempfile.mkdtemp(
                    prefix=f".{self.directory.name}-",
                    dir=self.directory.parent,
                )
            )
            try:
                self._generate(staging)
                try:
                    staging.rename(self.directory)

                except FileExistsError:
                    self._validate_complete_store()
            finally:

                if staging.exists():
                    shutil.rmtree(staging)

        except PkiError:
            raise

        except OSError as error:
            raise PkiError(
                f"Unable to initialize PKI at '{self.directory}': {error}"
            ) from error

        self._validate_complete_store()
        self._tighten_permissions()

    def read_ca_certificate(self) -> str:
        """Return the local CA certificate after validating the store."""
        self.ensure()
        try:
            return self.ca_certificate_path.read_text()

        except OSError as error:
            raise PkiError(f"Unable to read CA certificate: {error}") from error

    def issue_client_certificate(
        self,
        public_key: ec.EllipticCurvePublicKey,
    ) -> ClientCertificateBundle:
        """Issue a clientAuth certificate without copying CSR attributes."""
        self.ensure()
        try:
            ca_certificate = self._load_certificate(self.ca_certificate_path)
            ca_key = self._load_private_key(self.ca_private_key_path)

        except (OSError, TypeError, UnsupportedAlgorithm, ValueError) as error:
            raise PkiError(f"Unable to load CA identity: {error}") from error

        if not isinstance(ca_key, ec.EllipticCurvePrivateKey):
            raise PkiError("The CA private key is not an elliptic-curve key")

        now = datetime.now(UTC)
        certificate = (
            x509.CertificateBuilder()
            .subject_name(
                x509.Name(
                    [x509.NameAttribute(NameOID.COMMON_NAME, "sanex client")]
                )
            )
            .issuer_name(ca_certificate.subject)
            .public_key(public_key)
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(hours=1))
            .not_valid_after(now + self._CLIENT_LIFETIME)
            .add_extension(
                x509.BasicConstraints(ca=False, path_length=None),
                critical=True,
            )
            .add_extension(
                x509.KeyUsage(
                    digital_signature=True,
                    content_commitment=False,
                    key_encipherment=False,
                    data_encipherment=False,
                    key_agreement=False,
                    key_cert_sign=False,
                    crl_sign=False,
                    encipher_only=None,
                    decipher_only=None,
                ),
                critical=True,
            )
            .add_extension(
                x509.ExtendedKeyUsage([ExtendedKeyUsageOID.CLIENT_AUTH]),
                critical=False,
            )
            .add_extension(
                x509.SubjectKeyIdentifier.from_public_key(public_key),
                critical=False,
            )
            .add_extension(
                x509.AuthorityKeyIdentifier.from_issuer_public_key(
                    ca_key.public_key()
                ),
                critical=False,
            )
            .sign(ca_key, hashes.SHA256())
        )
        certificate_pem = certificate.public_bytes(
            serialization.Encoding.PEM
        ).decode()
        return ClientCertificateBundle(
            ca=ca_certificate.public_bytes(serialization.Encoding.PEM).decode(),
            certificate=certificate_pem,
            fingerprint=certificate.fingerprint(hashes.SHA256()).hex(),
        )

    def _generate(self, directory: Path) -> None:
        now = datetime.now(UTC)
        valid_from = now - timedelta(days=1)
        ca_key = ec.generate_private_key(ec.SECP256R1())
        ca_name = x509.Name(
            [x509.NameAttribute(NameOID.COMMON_NAME, "sanea local CA")]
        )
        ca_certificate = (
            x509.CertificateBuilder()
            .subject_name(ca_name)
            .issuer_name(ca_name)
            .public_key(ca_key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(valid_from)
            .not_valid_after(now + self._CA_LIFETIME)
            .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
            .add_extension(
                x509.KeyUsage(
                    digital_signature=True,
                    content_commitment=False,
                    key_encipherment=False,
                    data_encipherment=False,
                    key_agreement=False,
                    key_cert_sign=True,
                    crl_sign=True,
                    encipher_only=None,
                    decipher_only=None,
                ),
                critical=True,
            )
            .add_extension(
                x509.SubjectKeyIdentifier.from_public_key(ca_key.public_key()),
                critical=False,
            )
            .sign(ca_key, hashes.SHA256())
        )

        server_key = ec.generate_private_key(ec.SECP256R1())
        server_name = x509.Name(
            [x509.NameAttribute(NameOID.COMMON_NAME, "sanea")]
        )
        server_certificate = (
            x509.CertificateBuilder()
            .subject_name(server_name)
            .issuer_name(ca_certificate.subject)
            .public_key(server_key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(valid_from)
            .not_valid_after(now + self._SERVER_LIFETIME)
            .add_extension(
                x509.BasicConstraints(ca=False, path_length=None),
                critical=True,
            )
            .add_extension(
                x509.KeyUsage(
                    digital_signature=True,
                    content_commitment=False,
                    key_encipherment=False,
                    data_encipherment=False,
                    key_agreement=True,
                    key_cert_sign=False,
                    crl_sign=False,
                    encipher_only=False,
                    decipher_only=False,
                ),
                critical=True,
            )
            .add_extension(
                x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]),
                critical=False,
            )
            .add_extension(
                x509.SubjectAlternativeName(
                    [x509.DNSName("sanea"), x509.DNSName("localhost")]
                ),
                critical=False,
            )
            .add_extension(
                x509.SubjectKeyIdentifier.from_public_key(server_key.public_key()),
                critical=False,
            )
            .add_extension(
                x509.AuthorityKeyIdentifier.from_issuer_public_key(
                    ca_key.public_key()
                ),
                critical=False,
            )
            .sign(ca_key, hashes.SHA256())
        )

        self._write_private_key(directory / "ca.key", ca_key)
        self._write_certificate(directory / "ca.crt", ca_certificate)
        self._write_private_key(directory / "server.key", server_key)
        self._write_certificate(directory / "server.crt", server_certificate)

    def _validate_complete_store(self) -> None:
        missing = [
            path.name
            for path in self.paths
            if not path.is_file() or path.is_symlink()
        ]

        if missing:
            raise PkiError(
                f"Incomplete PKI directory '{self.directory}'; missing: "
                f"{", ".join(missing)}"
            )

        try:
            ca_certificate = self._load_certificate(self.ca_certificate_path)
            ca_key = self._load_private_key(self.ca_private_key_path)
            server_certificate = self._load_certificate(
                self.server_certificate_path
            )
            server_key = self._load_private_key(self.server_private_key_path)
            self._validate_certificates(
                ca_certificate,
                ca_key,
                server_certificate,
                server_key,
            )

        except PkiError:
            raise

        except (
            InvalidSignature,
            OSError,
            TypeError,
            UnsupportedAlgorithm,
            ValueError,
            x509.ExtensionNotFound,
        ) as error:
            raise PkiError(
                f"Invalid PKI directory '{self.directory}': {error}"
            ) from error

    def _validate_certificates(
        self,
        ca_certificate: x509.Certificate,
        ca_key: PrivateKeyTypes,
        server_certificate: x509.Certificate,
        server_key: PrivateKeyTypes,
    ) -> None:

        if not isinstance(ca_key, ec.EllipticCurvePrivateKey) or not isinstance(
            server_key,
            ec.EllipticCurvePrivateKey,
        ):
            raise PkiError("PKI private keys must be elliptic-curve keys")

        if not isinstance(ca_key.curve, ec.SECP256R1) or not isinstance(
            server_key.curve,
            ec.SECP256R1,
        ):
            raise PkiError("PKI private keys must use the P-256 curve")

        if not self._keys_match(ca_key, ca_certificate) or not self._keys_match(
            server_key,
            server_certificate,
        ):
            raise PkiError("A PKI certificate does not match its private key")

        if not ca_certificate.extensions.get_extension_for_class(
            x509.BasicConstraints
        ).value.ca:
            raise PkiError("The sanea CA certificate is not a CA")

        usages = server_certificate.extensions.get_extension_for_class(
            x509.ExtendedKeyUsage
        ).value

        if ExtendedKeyUsageOID.SERVER_AUTH not in usages:
            raise PkiError(
                "The server certificate is not valid for server authentication"
            )

        if ca_certificate.issuer != ca_certificate.subject:
            raise PkiError("The sanea CA certificate is not self-issued")

        ca_certificate.public_key().verify(
            ca_certificate.signature,
            ca_certificate.tbs_certificate_bytes,
            ec.ECDSA(ca_certificate.signature_hash_algorithm),
        )

        if server_certificate.issuer != ca_certificate.subject:
            raise PkiError("The server certificate was not issued by the sanea CA")

        ca_certificate.public_key().verify(
            server_certificate.signature,
            server_certificate.tbs_certificate_bytes,
            ec.ECDSA(server_certificate.signature_hash_algorithm),
        )

        now = datetime.now(UTC)

        for label, certificate in (
            ("CA", ca_certificate),
            ("server", server_certificate),
        ):

            if not (
                certificate.not_valid_before_utc
                <= now
                <= certificate.not_valid_after_utc
            ):
                raise PkiError(f"The {label} certificate is not currently valid")

    def _tighten_permissions(self) -> None:
        try:
            self.directory.chmod(0o700)
            self.ca_private_key_path.chmod(0o600)
            self.server_private_key_path.chmod(0o600)

        except OSError as error:
            raise PkiError(f"Unable to secure PKI permissions: {error}") from error

    @staticmethod
    def _load_certificate(path: Path) -> x509.Certificate:
        return x509.load_pem_x509_certificate(path.read_bytes())

    @staticmethod
    def _load_private_key(path: Path) -> PrivateKeyTypes:
        return serialization.load_pem_private_key(
            path.read_bytes(),
            password=None,
        )

    @staticmethod
    def _keys_match(private_key: PrivateKeyTypes, certificate: x509.Certificate) -> bool:
        encoding = serialization.Encoding.DER
        public_format = serialization.PublicFormat.SubjectPublicKeyInfo
        return private_key.public_key().public_bytes(
            encoding,
            public_format,
        ) == certificate.public_key().public_bytes(encoding, public_format)

    @staticmethod
    def _write_private_key(path: Path, key: PrivateKeyTypes) -> None:
        path.write_bytes(
            key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            )
        )
        path.chmod(0o600)

    @staticmethod
    def _write_certificate(path: Path, certificate: x509.Certificate) -> None:
        path.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
        path.chmod(0o644)
