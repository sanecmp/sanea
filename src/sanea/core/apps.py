"""Django application configuration for the sanea domain."""

from django.apps import AppConfig
from django.db.models.signals import post_migrate
from django.utils.translation import gettext_lazy as _


def _install_default_process_exclusions(sender: AppConfig, **kwargs: object) -> None:
    model = sender.get_model("PrcExclusion")
    model.install_defaults()


class SaneaCoreConfig(AppConfig):
    """Configure sanea's core relational models."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "sanea.core"
    verbose_name = _("Sanea")

    def ready(self) -> None:
        """Register the code-defined navigation tree and post-migration defaults."""
        # django-sitetree imports Django models and therefore must load only
        # after the application registry is ready.
        from sitetree.sitetreeapp import compose_dynamic_tree, register_dynamic_trees

        register_dynamic_trees(compose_dynamic_tree(self.name))
        post_migrate.connect(
            _install_default_process_exclusions,
            sender=self,
            dispatch_uid="sanea.install_default_process_exclusions",
        )
