"""Dynamic navigation trees for the sanea browser interface."""

from django.utils.translation import gettext_lazy as _
from sitetree.utils import item, tree


sitetrees = (
    tree(
        "main",
        items=(
            item(
                _("Dashboard"),
                "core:dashboard",
                alias="dashboard",
                access_loggedin=True,
            ),
            item(
                _("People"),
                "core:people",
                alias="people",
                access_loggedin=True,
            ),
            item(
                _("Computers"),
                "core:computers",
                alias="computers",
                access_loggedin=True,
            ),
            item(
                _("Accounts"),
                "core:accounts",
                alias="accounts",
                access_loggedin=True,
            ),
            item(
                _("Limits"),
                "core:limits",
                alias="limits",
                access_loggedin=True,
            ),
            item(
                _("Issues"),
                "core:issues",
                alias="issues",
                access_loggedin=True,
            ),
            item(
                _("Settings"),
                "core:ignored_processes",
                alias="settings",
                access_loggedin=True,
            ),
        ),
    ),
)
