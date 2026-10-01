"""
Core App Configuration for Platform Backoffice
"""
from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'core'
    verbose_name = 'Platform Core'

    def ready(self):
        # Register system checks
        import core.checks  # noqa
        
        # Discover and register all module manifests
        from core.registry import module_registry
        module_registry.autodiscover()
