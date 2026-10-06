"""UDP discovery listener for sanex clients on the local network."""

import json
import socket
import threading
from collections.abc import Callable


DISCOVERY_REQUEST = b"SANEA-DISCOVER"
REGISTRATION_REQUEST = b"SANEA-REGISTER"
MAX_REQUEST_SIZE = 64


class DiscoveryServer:
    """Answer supported UDP probes with the configured HTTPS port."""

    def __init__(
        self,
        host: str,
        port: int,
        https_port: int,
        registration_available: Callable[[], bool],
    ) -> None:
        self.bind_addr = (host, port)
        self._https_port = https_port
        self._registration_available = registration_available
        self._stop_requested = threading.Event()
        self._socket: socket.socket | None = None
        self._response = json.dumps(
            {"port": https_port},
            separators=(",", ":"),
        ).encode()

    def prepare(self) -> None:
        """Bind the UDP socket before the serving thread starts."""
        bind_addr = self.bind_addr
        udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            udp_socket.settimeout(0.2)
            udp_socket.bind(bind_addr)

        except BaseException:
            udp_socket.close()
            raise

        self._socket = udp_socket
        setattr(self, "bind_addr", udp_socket.getsockname())

    def serve(self) -> None:
        """Receive discovery probes until shutdown is requested."""
        udp_socket = self._socket

        if udp_socket is None:
            raise RuntimeError("UDP discovery server is not prepared")

        stop_requested = self._stop_requested
        response = self._response
        try:

            while not stop_requested.is_set():
                try:
                    request, sender = udp_socket.recvfrom(MAX_REQUEST_SIZE + 1)

                except TimeoutError:
                    continue

                if self._should_respond(request):
                    udp_socket.sendto(response, sender)
        finally:
            udp_socket.close()
            setattr(self, "_socket", None)

    def stop(self) -> None:
        """Ask the listener to stop after its current receive timeout."""
        self._stop_requested.set()

    def _should_respond(self, request: bytes) -> bool:

        if request == DISCOVERY_REQUEST:
            return True

        if request == REGISTRATION_REQUEST:
            return self._registration_available()

        return False
