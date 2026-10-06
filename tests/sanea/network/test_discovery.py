"""Tests for UDP discovery behavior with a substituted transport."""

from collections import deque
from collections.abc import Callable

import pytest

from sanea.network import discovery
from sanea.network.discovery import DISCOVERY_REQUEST, REGISTRATION_REQUEST, DiscoveryServer


class DatagramSocket:
    def __init__(self, requests: list[bytes | OSError]) -> None:
        self.requests = deque(requests)
        self.sent: list[tuple[bytes, tuple[str, int]]] = []
        self.bound: tuple[str, int] | None = None
        self.timeout: float | None = None
        self.closed = False
        self.stop: Callable[[], None] = lambda: None
        self.send_error: OSError | None = None
        self.bind_error: OSError | None = None

    def settimeout(self, timeout: float) -> None:
        self.timeout = timeout

    def bind(self, address: tuple[str, int]) -> None:

        if self.bind_error is not None:
            raise self.bind_error

        self.bound = address

    def getsockname(self) -> tuple[str, int]:
        return ("127.0.0.1", 32117)

    def recvfrom(self, size: int) -> tuple[bytes, tuple[str, int]]:
        assert size == discovery.MAX_REQUEST_SIZE + 1

        if not self.requests:
            self.stop()
            raise TimeoutError

        request = self.requests.popleft()

        if isinstance(request, OSError):
            raise request

        return request, ("127.0.0.1", 32118)

    def sendto(self, response: bytes, sender: tuple[str, int]) -> None:

        if self.send_error is not None:
            raise self.send_error

        self.sent.append((response, sender))

    def close(self) -> None:
        self.closed = True


def listener(
    monkeypatch: pytest.MonkeyPatch,
    requests: list[bytes | OSError],
    *,
    registration_available: bool = False,
) -> tuple[DiscoveryServer, DatagramSocket]:
    transport = DatagramSocket(requests)

    def create_socket(family: int, kind: int) -> DatagramSocket:
        assert family == discovery.socket.AF_INET
        assert kind == discovery.socket.SOCK_DGRAM
        return transport

    monkeypatch.setattr(discovery.socket, "socket", create_socket)
    server = DiscoveryServer("127.0.0.1", 0, 18_443, lambda: registration_available)
    transport.stop = server.stop
    return server, transport


@pytest.mark.parametrize(
    ("payload", "available", "response_count"),
    [
        pytest.param(DISCOVERY_REQUEST, False, 1, id="discovery"),
        pytest.param(REGISTRATION_REQUEST, True, 1, id="registration-open"),
        pytest.param(REGISTRATION_REQUEST, False, 0, id="registration-closed"),
        pytest.param(b"UNKNOWN", False, 0, id="unknown"),
        pytest.param(b"X" * 65, False, 0, id="oversized"),
    ],
)
def test_discovery_answers_supported_requests(
    monkeypatch: pytest.MonkeyPatch,
    payload: bytes,
    available: bool,
    response_count: int,
) -> None:
    server, transport = listener(monkeypatch, [payload], registration_available=available)

    server.prepare()
    server.serve()

    assert transport.bound == ("127.0.0.1", 0)
    assert server.bind_addr == ("127.0.0.1", 32117)
    assert transport.timeout == 0.2
    assert transport.sent == [(b"{\"port\":18443}", ("127.0.0.1", 32118))] * response_count
    assert transport.closed


def test_discovery_continues_after_receive_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    server, transport = listener(monkeypatch, [TimeoutError(), DISCOVERY_REQUEST])

    server.prepare()
    server.serve()

    assert transport.sent == [(b"{\"port\":18443}", ("127.0.0.1", 32118))]
    assert transport.closed


@pytest.mark.parametrize("failure", ["bind", "receive", "send"])
def test_discovery_closes_socket_after_transport_error(
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
) -> None:
    error = OSError("synthetic UDP failure")
    requests = [error] if failure == "receive" else [DISCOVERY_REQUEST]
    server, transport = listener(monkeypatch, requests)

    if failure == "bind":
        transport.bind_error = error

    if failure == "send":
        transport.send_error = error

    with pytest.raises(OSError, match="synthetic UDP failure"):
        server.prepare()
        server.serve()

    assert transport.closed


def test_discovery_requires_preparation() -> None:
    server = DiscoveryServer("127.0.0.1", 0, 18_443, lambda: False)

    with pytest.raises(RuntimeError, match="UDP discovery server is not prepared"):
        server.serve()
