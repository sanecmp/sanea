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
                _("Statistics"),
                "core:statistics",
                alias="statistics",
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
                children=(
                    item(_("Command history"), "core:computer_commands", in_menu=False, access_loggedin=True),
                    item(_("Updates"), "core:computer_updates", in_menu=False, access_loggedin=True),
                ),
            ),
            item(
                _("Accounts"),
                "core:accounts",
                alias="accounts",
                access_loggedin=True,
                children=(
                    item(
                        "{{ account.get_display_name }}", "core:account_limits account.pk",
                        in_menu=False, access_loggedin=True,
                        children=(
                            item(
                                _("Remove restriction"), "core:account_rule_delete account.pk deletion.kind deletion.rule_pk",
                                in_menu=False, access_loggedin=True,
                            ),
                        ),
                    ),
                ),
            ),
            item(
                _("Limits"),
                "core:limits",
                alias="limits",
                access_loggedin=True,
                children=(
                    item(_("Schedule ranges"), "core:ranges limits.pk", in_menu=False, access_loggedin=True),
                    item(
                        _("Session rules"), "core:session_rules limits.pk", in_menu=False, access_loggedin=True,
                        children=(
                            item(
                                _("Application rules"), "core:app_rules limits.pk session_rule.pk",
                                in_menu=False, access_loggedin=True,
                            ),
                        ),
                    ),
                ),
            ),
        ),
    ),
)
