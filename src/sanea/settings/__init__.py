"""Django settings selected and populated through envbox."""

from envbox import import_by_environment

from .environment import ENVIRONMENT


import_by_environment(
    ENVIRONMENT,
    module_name_pattern="env_%s",
    package_name=__package__,
)
