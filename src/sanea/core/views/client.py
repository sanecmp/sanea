"""HTTP endpoints used by sanex clients."""

import logging
from collections.abc import Callable
from functools import wraps
from typing import ParamSpec

from django.core.exceptions import RequestDataTooBig
from django.db import DatabaseError
from django.http import HttpRequest, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods, require_POST
from pydantic import ValidationError as PydanticValidationError
from sanelib.protocol import (
    RegistrationConfirmResponse,
    RegistrationIssueResponse,
    SyncResponse,
    encode_registration_message,
    encode_sync_response,
)

from ...exceptions import (
    ClientAccessError,
    ClientPayloadTooLargeError,
    ClientRequestError,
    ComputerConfigError,
    EventSequenceConflictError,
    PkiError,
)
from ..client import (
    parse_event_packet,
    parse_log_tail,
    parse_registration_confirm_request,
    parse_registration_request,
    parse_sync_request,
)
from ..client.authentication import computer_from_verified_certificate
from ..services.client_registration import (
    ClientRegistrationConfirmResult,
    ClientRegistrationResult,
    confirm_client_registration,
    register_client,
)
from ..services.client_sync import ClientSyncResult, synchronize_client
from ..services.registration_window import registration_window


logger = logging.getLogger(__name__)
Params = ParamSpec("Params")


def _error_response(status: int) -> HttpResponse:
    return HttpResponse(status=status)


def handle_client_errors(
    operation: str,
) -> Callable[[Callable[Params, HttpResponse]], Callable[Params, HttpResponse]]:
    """Map expected client failures without hiding implementation errors."""

    def decorate(
        view: Callable[Params, HttpResponse],
    ) -> Callable[Params, HttpResponse]:
        @wraps(view)
        def wrapped(*args: Params.args, **kwargs: Params.kwargs) -> HttpResponse:
            try:
                return view(*args, **kwargs)

            except ClientAccessError:
                return _error_response(403)

            except (ClientPayloadTooLargeError, RequestDataTooBig):
                return _error_response(413)

            except EventSequenceConflictError:
                return _error_response(409)

            except ClientRequestError:
                return _error_response(422)

            except (
                ComputerConfigError,
                PkiError,
                PydanticValidationError,
                DatabaseError,
            ):
                logger.exception("Unable to %s", operation)
                return _error_response(503)

        return wrapped

    return decorate


def _registration_response(result: ClientRegistrationResult) -> HttpResponse:
    response = RegistrationIssueResponse(
        ca=result.ca,
        certificate=result.certificate,
    )
    return HttpResponse(
        encode_registration_message(response),
        status=201,
        content_type="application/json",
    )


def _registration_confirm_response(
    result: ClientRegistrationConfirmResult,
) -> HttpResponse:
    response = RegistrationConfirmResponse(config=result.config.decode())
    return HttpResponse(
        encode_registration_message(response),
        content_type="application/json",
    )


def _sync_response(
    result: ClientSyncResult,
    client_config_ident: int | None,
) -> HttpResponse:
    config = (
        None
        if client_config_ident == result.config.ident
        else result.config.decode()
    )
    response = SyncResponse(
        config=config,
        commands=tuple(
            command.build_client_command() for command in result.commands
        ),
    )
    return HttpResponse(
        encode_sync_response(response),
        content_type="application/json",
    )


@csrf_exempt
@require_POST
@handle_client_errors("register sanex client")
def client_register(request: HttpRequest) -> HttpResponse:
    """Issue a certificate to the first valid CSR in an open window."""

    if not request.is_secure():
        return _error_response(403)

    if request.content_type != "application/json":
        return _error_response(422)

    registration_request = parse_registration_request(request.body)
    result = register_client(registration_request, registration_window)
    return _registration_response(result)


@csrf_exempt
@require_POST
@handle_client_errors("confirm sanex client registration")
def client_register_confirm(request: HttpRequest) -> HttpResponse:
    """Apply initial sanex state and complete an mTLS registration."""
    computer = computer_from_verified_certificate(request)

    if computer is None:
        return _error_response(403)

    if request.content_type != "application/json":
        return _error_response(422)

    confirmation = parse_registration_confirm_request(request.body)
    result = confirm_client_registration(
        computer,
        confirmation,
        request.META.get("REMOTE_ADDR"),
    )
    return _registration_confirm_response(result)


@csrf_exempt
@require_POST
@handle_client_errors("synchronize sanex client")
def client_sync(request: HttpRequest) -> HttpResponse:
    """Apply one authenticated sanex state snapshot and return control data."""
    computer = computer_from_verified_certificate(request)

    if computer is None:
        return _error_response(403)

    if request.content_type != "application/json":
        return _error_response(422)

    sync_request = parse_sync_request(request.body)
    result = synchronize_client(
        computer,
        sync_request,
        request.META.get("REMOTE_ADDR"),
    )
    return _sync_response(result, sync_request.config_ident)


@csrf_exempt
@require_POST
@handle_client_errors("save sanex event packet")
def client_events(
    request: HttpRequest,
    uid: int,
    sha256: str,
) -> HttpResponse:
    """Store one authenticated immutable sanex event packet."""
    computer = computer_from_verified_certificate(request)

    if computer is None:
        return _error_response(403)

    computer.ensure_synchronization_allowed()

    if request.content_type != "application/x-ndjson":
        return _error_response(422)

    account = computer.accounts.filter(uid=uid).first()

    if account is None:
        return _error_response(404)

    if not account.collect:
        return _error_response(403)

    body = request.body
    packet = parse_event_packet(body, sha256)
    _, created = account.store_event_packet(
        packet,
        len(body),
        request.META.get("REMOTE_ADDR"),
    )

    return HttpResponse(status=201 if created else 204)


@csrf_exempt
@require_http_methods(["PUT"])
@handle_client_errors("save sanex technical log")
def client_log(request: HttpRequest) -> HttpResponse:
    """Replace the latest technical-log snapshot from an authenticated sanex."""
    computer = computer_from_verified_certificate(request)

    if computer is None:
        return _error_response(403)

    if request.content_type != "text/plain":
        return _error_response(422)

    content = parse_log_tail(request.body)
    computer.replace_log_tail(content, request.META.get("REMOTE_ADDR"))

    return HttpResponse(status=204)
