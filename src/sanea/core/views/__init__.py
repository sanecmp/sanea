"""Views exposed by the sanea core application."""

from .accounts import accounts
from .app_rules import app_rules
from .authentication import sign_in, sign_out
from .client import client_events, client_log, client_register, client_register_confirm, client_sync
from .computers import computers
from .dashboard import dashboard
from .issues import issues
from .ignored_processes import ignored_processes
from .limits import limits
from .people import people
from .ranges import ranges
from .session_rules import session_rules


__all__ = [
    "accounts",
    "app_rules",
    "client_events",
    "client_log",
    "client_register",
    "client_register_confirm",
    "client_sync",
    "computers",
    "dashboard",
    "issues",
    "ignored_processes",
    "limits",
    "people",
    "ranges",
    "session_rules",
    "sign_in",
    "sign_out",
]
