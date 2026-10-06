"""Embedded HTTP and HTTPS servers for sanea."""

import hashlib
import ssl
import threading
from collections.abc import Callable
from pathlib import Path
from queue import Empty, SimpleQueue
from typing import Any, Protocol
from wsgiref.types import WSGIApplication

from cheroot.ssl.builtin import BuiltinSSLAdapter
from cheroot.wsgi import Server

from ..core.client.authentication import VERIFIED_CERTIFICATE_FINGERPRINT_META
from ..exceptions import ServerError
from ..utils.pki import PkiStore
from .discovery import DiscoveryServer


class _Server(Protocol):
    """Cheroot operations used by the process-level server runner."""

    bind_addr: tuple[str, int]

    def prepare(self) -> None: ...

    def serve(self) -> None: ...

    def stop(self) -> None: ...


class ClientCertificateSSLAdapter(BuiltinSSLAdapter):
    """Expose the fingerprint of a client certificate verified by TLS."""

    def get_environ(self, sock: ssl.SSLSocket) -> dict[str, Any]:
        """Add a private identity value which cannot originate in HTTP headers."""
        environ = super().get_environ(sock)

        if environ.get("SSL_CLIENT_VERIFY") == "SUCCESS":
            certificate = sock.getpeercert(binary_form=True)

            if certificate:
                environ[VERIFIED_CERTIFICATE_FINGERPRINT_META] = hashlib.sha256(
                    certificate
                ).hexdigest()

        return environ


def create_tls_adapter(pki_dir: Path) -> ClientCertificateSSLAdapter:
    """Create a server TLS adapter which optionally verifies client certificates."""
    paths = {
        "CA certificate": pki_dir / "ca.crt",
        "server certificate": pki_dir / "server.crt",
        "server private key": pki_dir / "server.key",
    }
    missing = [
        f"{label}: {path}"
        for label, path in paths.items()
        if not path.is_file()
    ]

    if missing:
        raise ServerError(f"Missing TLS files: {", ".join(missing)}")

    try:
        adapter = ClientCertificateSSLAdapter(
            f"{paths["server certificate"]}",
            f"{paths["server private key"]}",
            f"{paths["CA certificate"]}",
        )

    except (OSError, ssl.SSLError) as error:
        raise ServerError(f"Unable to configure TLS: {error}") from error

    adapter.context.verify_mode = ssl.CERT_OPTIONAL
    adapter.context.minimum_version = ssl.TLSVersion.TLSv1_2
    return adapter


def create_servers(
    application: WSGIApplication,
    host: str,
    http_port: int,
    https_port: int,
    discovery_port: int,
    pki_dir: Path,
    registration_available: Callable[[], bool],
) -> tuple[Server, Server, DiscoveryServer]:
    """Create HTTP, HTTPS and UDP discovery listeners."""
    PkiStore(pki_dir).ensure()
    http_server = Server((host, http_port), application)
    https_server = Server((host, https_port), application)
    https_server.ssl_adapter = create_tls_adapter(pki_dir)
    discovery_server = DiscoveryServer(
        host,
        discovery_port,
        https_port,
        registration_available,
    )
    return http_server, https_server, discovery_server


class ServerRunner:
    """Run and stop several Cheroot listeners as one application."""

    def __init__(self, servers: tuple[_Server, ...]) -> None:
        self._servers = servers
        self._stop_requested = threading.Event()
        self._errors: SimpleQueue[BaseException] = SimpleQueue()
        self._threads: list[threading.Thread] = []

    def request_stop(self) -> None:
        """Ask the main loop to stop all listeners."""
        self._stop_requested.set()

    def run(self) -> None:
        """Prepare listeners, serve concurrently and shut all of them down together."""
        prepared: list[_Server] = []
        servers = self._servers
        threads = self._threads
        stop_requested = self._stop_requested
        serve = self._serve
        startup_error: Exception | None = None
        try:

            for server in servers:
                server.prepare()
                prepared.append(server)

            for server in servers:
                thread = threading.Thread(
                    target=serve,
                    args=(server,),
                    name=f"sanea-{server.bind_addr[1]}",
                )
                thread.start()
                threads.append(thread)

            while not stop_requested.wait(0.2):

                if any(not thread.is_alive() for thread in threads):
                    break

        except (OSError, ValueError) as error:
            startup_error = error
        finally:
            shutdown_error = self._stop_servers(prepared, threads)

        if startup_error is not None:
            raise ServerError(f"Unable to start server: {startup_error}") from startup_error

        try:
            error = self._errors.get_nowait()

        except Empty:

            if shutdown_error is not None:
                raise ServerError(
                    f"Unable to stop server cleanly: {shutdown_error}"
                ) from shutdown_error

        else:
            raise ServerError(f"Server stopped unexpectedly: {error}") from error

    @staticmethod
    def _stop_servers(
        servers: list[_Server],
        threads: list[threading.Thread],
    ) -> BaseException | None:
        """Stop every prepared listener and retain the first cleanup failure."""
        errors: list[BaseException] = []

        for server in reversed(servers):
            try:
                server.stop()

            except BaseException as error:
                errors.append(error)

        for thread in threads:
            try:
                thread.join()

            except BaseException as error:
                errors.append(error)

        return errors[0] if errors else None

    def _serve(self, server: _Server) -> None:
        try:
            server.serve()

        except BaseException as error:
            self._errors.put(error)
        finally:
            self._stop_requested.set()
