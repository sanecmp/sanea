"""Views exposed by the sanea core application."""

from .accounts import accounts
from .account_limits import account_limits, account_rule_delete
from .app_rules import app_rules
from .authentication import sign_in, sign_out
from .client import client_events, client_log, client_register, client_register_confirm, client_sync
from .computers import computers
from .computer_commands import computer_commands
from .computer_updates import computer_updates
from .dashboard import dashboard
from .limits import limits
from .people import people
from .ranges import ranges
from .session_rules import session_rules
from .statistics import statistics


__all__ = [
    "account_limits",
    "account_rule_delete",
    "accounts",
    "app_rules",
    "client_events",
    "client_log",
    "client_register",
    "client_register_confirm",
    "client_sync",
    "computers",
    "computer_commands",
    "computer_updates",
    "dashboard",
    "limits",
    "people",
    "ranges",
    "session_rules",
    "sign_in",
    "sign_out",
    "statistics",
]
