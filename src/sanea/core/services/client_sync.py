"""Transactional handling of one sanex synchronization request."""

from dataclasses import dataclass

from django.db import transaction
from sanelib.protocol import SyncRequest

from ..models import ClientCommand, Computer, ComputerConfig, GlobalUpdate


@dataclass(frozen=True, slots=True)
class ClientSyncResult:
    """Ready configuration and still-pending commands for one response."""

    config: ComputerConfig
    commands: tuple[ClientCommand, ...]


@transaction.atomic
def synchronize_client(
    computer: Computer,
    request: SyncRequest,
    remote_ip: str | None,
) -> ClientSyncResult:
    """Apply client state and return the resulting control response data."""
    locked_computer = Computer.objects.select_for_update().get(pk=computer.pk)
    locked_computer.ensure_synchronization_allowed()

    locked_computer.update_contact(
        request.version,
        remote_ip,
        hostname=request.hostname,
    )
    locked_computer.acknowledge_config(request.config_ident)

    accounts = request.accounts

    if accounts is not None:
        locked_computer.apply_account_snapshot(accounts)

    locked_computer.apply_command_results(request.command_results)
    active_update = GlobalUpdate.get_active()

    if active_update is not None:
        active_update.ensure_command(locked_computer)

    config = locked_computer.materialize_config()
    commands = tuple(
        ClientCommand.objects.filter(
            computer=locked_computer,
            status__isnull=True,
        ).order_by("pk")
    )
    return ClientSyncResult(config=config, commands=commands)
