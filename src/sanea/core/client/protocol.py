"""Sanea adapters for the shared sanex wire protocol."""

from collections.abc import Callable

from sanelib import protocol as shared_protocol
from sanelib.exceptions import PayloadTooLargeError, ProtocolError

from ...exceptions import ClientPayloadTooLargeError, ClientRequestError


def parse_event_packet(data: bytes, expected_sha256: str) -> shared_protocol.ParsedEventPacket:
    """Decode a bounded event packet using sanea exceptions."""
    try:
        return shared_protocol.parse_event_packet(data, expected_sha256)

    except PayloadTooLargeError as error:
        raise ClientPayloadTooLargeError(error.detail) from error

    except ProtocolError as error:
        raise ClientRequestError(error.detail) from error


def parse_registration_request(data: bytes) -> shared_protocol.RegistrationRequest:
    """Decode a registration request using sanea exceptions."""
    return _parse_client_message(shared_protocol.parse_registration_request, data)


def parse_registration_confirm_request(data: bytes) -> shared_protocol.RegistrationConfirmRequest:
    """Decode a registration confirmation using sanea exceptions."""
    return _parse_client_message(shared_protocol.parse_registration_confirm_request, data)


def parse_sync_request(data: bytes) -> shared_protocol.SyncRequest:
    """Decode a synchronization request using sanea exceptions."""
    return _parse_client_message(shared_protocol.parse_sync_request, data)


def parse_log_tail(data: bytes) -> str:
    """Decode a bounded technical-log snapshot using sanea exceptions."""
    try:
        return shared_protocol.decode_log_tail(data)

    except PayloadTooLargeError as error:
        raise ClientPayloadTooLargeError(error.detail) from error

    except ProtocolError as error:
        raise ClientRequestError(error.detail) from error


def _parse_client_message[MessageT](
    parser: Callable[[bytes], MessageT],
    data: bytes,
) -> MessageT:
    try:
        return parser(data)

    except ProtocolError as error:
        raise ClientRequestError(error.detail) from error
