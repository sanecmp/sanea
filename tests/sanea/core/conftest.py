"""Shared synthetic activity for reports and browser views."""

import hashlib
import json
from collections.abc import Callable

import pytest
from django.db.models import Max
from sanelib.protocol import parse_event_packet

from sanea.core.models import Account


@pytest.fixture
def activity_run_create() -> Callable[..., None]:
    """Store a synthetic session or application run through the packet API."""

    def create(
        account: Account,
        *,
        started: int,
        finished: int | None,
        duration: int = 0,
        kind: str = "session",
        prc_name: str = "synthetic-app",
        exe: str = "/demo/synthetic-app",
    ) -> None:
        seq = (account.activity_events.aggregate(latest=Max("seq"))["latest"] or 0) + 1
        start = {
            "seq": seq,
            "run_ident": seq,
            "type": f"{kind}_start",
            "timestamp": started,
            "meta": {"existing": False} if kind == "session" else {"observed_via": "atspi"},
        }

        if kind == "session":
            start["sess_ident"] = f"synthetic-{seq}"

        else:
            start.update(prc_name=prc_name, exe=exe)

        events = [start]

        if finished is not None:
            events.append({
                "seq": seq + 1,
                "run_ident": seq,
                "type": f"{kind}_end",
                "timestamp": finished,
                "duration": duration,
                "meta": {"actor": "user"},
            })

        content = ("\n".join(json.dumps(event) for event in events) + "\n").encode()
        packet = parse_event_packet(content, hashlib.sha256(content).hexdigest())
        account.store_event_packet(packet, len(content), None)

    return create
