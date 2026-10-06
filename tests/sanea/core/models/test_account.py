"""Tests for local operating-system accounts and their limits ownership."""

from typing import Any

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from sanea.core.models.account import Account
from sanea.core.models.computer import Computer


def test_new_account_is_not_observed(domain_payload: dict[str, Any]) -> None:
    computer = Computer.objects.create(hostname="another-laptop")
    account = Account.objects.create(
        computer=computer,
        uid=domain_payload["account"]["uid"],
        login=domain_payload["account"]["login"],
        name=domain_payload["account"]["name"],
    )

    assert account.collect is False
    assert account.apply is False
    assert account.present is True


def test_identity_is_computer_and_uid(domain_graph: dict[str, Any]) -> None:
    account = domain_graph["account"]

    with pytest.raises(IntegrityError), transaction.atomic():
        Account.objects.create(
            computer=account.computer,
            uid=account.uid,
            login="renamed",
            name="Renamed",
        )


def test_applying_limits_requires_collection_and_limits(domain_graph: dict[str, Any]) -> None:
    account = domain_graph["account"]
    account.collect = False
    account.limits = None

    with pytest.raises(ValidationError) as error:
        account.full_clean()

    assert set(error.value.message_dict) == {"apply", "limits"}


def test_template_snapshot_can_be_shared(domain_graph: dict[str, Any]) -> None:
    account = domain_graph["account"]
    account.limits = domain_graph["template_limits"]

    account.full_clean()

    assert account.limits == domain_graph["template"].current_limits
