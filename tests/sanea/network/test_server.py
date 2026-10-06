"""Tests for the embedded Cheroot server."""

import hashlib
import ssl
import threading
from pathlib import Path
from unittest.mock import Mock
from wsgiref.types import StartResponse, WSGIEnvironment

import pytest
from cheroot.ssl.builtin import BuiltinSSLAdapter

from sanea.core.client import VERIFIED_CERTIFICATE_FINGERPRINT_META
from sanea.exceptions import ServerError
from sanea.network.discovery import DiscoveryServer
from sanea.network.server import ClientCertificateSSLAdapter, ServerRunner, create_servers, create_tls_adapter


def test_tls_adapter_requires_complete_pki(tmp_path: Path) -> None:

    with pytest.raises(ServerError, match="Missing TLS files"):
        create_tls_adapter(tmp_path)


def test_server_creation_initializes_pki(tmp_path: Path) -> None:
    pki_dir = tmp_path / "pki"

    def application(environ: WSGIEnvironment, start_response: StartResponse) -> tuple[bytes, ...]:
        return ()

    http_server, https_server, discovery_server = create_servers(
        application,
        "127.0.0.1",
        8000,
        8443,
        62_117,
        pki_dir,
        lambda: False,
    )

    assert http_server.ssl_adapter is None
    assert isinstance(https_server.ssl_adapter, ClientCertificateSSLAdapter)
    assert isinstance(discovery_server, DiscoveryServer)
    assert https_server.ssl_adapter.context.verify_mode == ssl.CERT_OPTIONAL
    assert https_server.ssl_adapter.context.minimum_version == ssl.TLSVersion.TLSv1_2
    assert (pki_dir / "ca.key").is_file()
    assert (pki_dir / "server.key").is_file()


@pytest.mark.parametrize(
    ("verification", "certificate", "identified"),
    [
        pytest.param("SUCCESS", b"synthetic-verified-certificate", True, id="verified"),
        pytest.param("SUCCESS", b"", False, id="missing-certificate"),
        pytest.param("NONE", b"unverified-certificate", False, id="unverified"),
    ],
)
def test_tls_adapter_exposes_only_verified_client_identity(
    verification: str,
    certificate: bytes,
    identified: bool,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    base_environ = Mock(return_value={"SSL_CLIENT_VERIFY": verification, "HTTPS": "on"})
    monkeypatch.setattr(BuiltinSSLAdapter, "get_environ", base_environ)
    tls_socket = Mock(spec=ssl.SSLSocket)
    tls_socket.getpeercert.return_value = certificate
    adapter = ClientCertificateSSLAdapter.__new__(ClientCertificateSSLAdapter)

    environ = adapter.get_environ(tls_socket)

    base_environ.assert_called_once_with(tls_socket)
    assert environ["SSL_CLIENT_VERIFY"] == verification
    assert environ["HTTPS"] == "on"

    if identified:
        assert environ[VERIFIED_CERTIFICATE_FINGERPRINT_META] == hashlib.sha256(certificate).hexdigest()

    else:
        assert VERIFIED_CERTIFICATE_FINGERPRINT_META not in environ

    if verification == "SUCCESS":
        tls_socket.getpeercert.assert_called_once_with(binary_form=True)

    else:
        tls_socket.getpeercert.assert_not_called()


class _FakeServer:
    def __init__(
        self,
        port: int,
        error: BaseException | None = None,
        stop_error: BaseException | None = None,
    ) -> None:
        self.bind_addr = ("127.0.0.1", port)
        self.error = error
        self.stop_error = stop_error
        self.prepared = False
        self.serving = threading.Event()
        self.stopped = threading.Event()

    def prepare(self) -> None:
        self.prepared = True

    def serve(self) -> None:
        self.serving.set()

        if self.error is not None:
            raise self.error

        self.stopped.wait()

    def stop(self) -> None:
        self.stopped.set()

        if self.stop_error is not None:
            raise self.stop_error


def test_server_runner_stops_both_listeners() -> None:
    servers = (_FakeServer(8000), _FakeServer(8443))
    runner = ServerRunner(servers)
    thread = threading.Thread(target=runner.run)
    thread.start()
    assert all(server.serving.wait(1) for server in servers)

    runner.request_stop()
    thread.join(2)

    assert not thread.is_alive()
    assert all(server.prepared for server in servers)
    assert all(server.stopped.is_set() for server in servers)


def test_server_runner_reports_listener_failure() -> None:
    servers = (_FakeServer(8000, RuntimeError("listener failed")), _FakeServer(8443))

    with pytest.raises(ServerError, match="listener failed"):
        ServerRunner(servers).run()

    assert all(server.stopped.is_set() for server in servers)


def test_server_runner_stops_remaining_listeners_after_cleanup_failure() -> None:
    servers = (
        _FakeServer(8000, stop_error=OSError("stop failed")),
        _FakeServer(8443),
    )
    runner = ServerRunner(servers)
    errors: list[BaseException] = []

    def run() -> None:
        try:
            runner.run()

        except BaseException as error:
            errors.append(error)

    thread = threading.Thread(target=run)
    thread.start()
    assert all(server.serving.wait(1) for server in servers)

    runner.request_stop()
    thread.join(2)

    assert not thread.is_alive()
    assert all(server.stopped.is_set() for server in servers)
    assert len(errors) == 1
    assert isinstance(errors[0], ServerError)
    assert "stop failed" in f"{errors[0]}"
