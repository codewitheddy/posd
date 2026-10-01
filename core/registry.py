"""
Module Registry and Manifest Discovery Engine
Handles module declarations, dynamic menus, dashboard cards, dependencies, and health checks.
"""
import importlib
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

from django.apps import apps
from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)


@dataclass
class MenuItem:
    """Individual menu item in the navigation sidebar."""
    title: str
    url_name: str
    icon: str = 'bi bi-circle'
    permission: Optional[str] = None
    badge: Optional[str] = None
    badge_class: str = 'badge bg-primary'
    order: int = 100
    children: List['MenuItem'] = field(default_factory=list)


@dataclass
class MenuSection:
    """Section / group of menu items."""
    title: str
    order: int = 100
    items: List[MenuItem] = field(default_factory=list)


@dataclass
class DashboardCard:
    """Widget / KPI Card displayed on the modular platform dashboard."""
    key: str
    title: str
    template_name: str
    context_callback: Optional[Callable[..., Dict[str, Any]]] = None
    permission: Optional[str] = None
    width: str = 'col-xl-3 col-md-6 mb-4'
    order: int = 100


@dataclass
class HealthCheck:
    """Module health check hook."""
    name: str
    check_callback: Callable[[], Tuple[bool, str]]


@dataclass
class ModuleManifest:
    """
    Complete manifest describing a pluggable business module.
    Each module defines this in its `module.py` file.
    """
    key: str
    name: str
    version: str = '1.0.0'
    description: str = ''
    icon: str = 'bi bi-boxes'
    dependencies: List[str] = field(default_factory=list)
    permission_prefix: str = ''
    default_roles: Dict[str, List[str]] = field(default_factory=dict)
    menu_sections: List[MenuSection] = field(default_factory=list)
    dashboard_cards: List[DashboardCard] = field(default_factory=list)
    settings_schema: Dict[str, Any] = field(default_factory=dict)
    event_subscriptions: Dict[str, Any] = field(default_factory=dict)
    health_checks: List[HealthCheck] = field(default_factory=list)
    url_prefix: str = ''
    is_core: bool = False


class ModuleRegistry:
    """
    Central singleton registry of all discovered modules.
    """

    def __init__(self):
        self._modules: Dict[str, ModuleManifest] = {}
        self._discovered = False

    def register(self, manifest: ModuleManifest) -> None:
        """Register a module manifest."""
        if manifest.key in self._modules:
            logger.warning("Module with key '%s' is already registered. Overwriting.", manifest.key)
        self._modules[manifest.key] = manifest
        logger.debug("Registered module: %s (v%s)", manifest.name, manifest.version)

    def get(self, key: str) -> Optional[ModuleManifest]:
        """Get a registered module by key."""
        return self._modules.get(key)

    def get_all(self) -> List[ModuleManifest]:
        """Return all registered modules ordered by core status and name."""
        return sorted(self._modules.values(), key=lambda m: (not m.is_core, m.name))

    def autodiscover(self) -> None:
        """
        Scan all INSTALLED_APPS for a `module.py` containing a manifest.
        """
        if self._discovered:
            return

        for app_config in apps.get_app_configs():
            app_name = app_config.name
            try:
                module_spec = f"{app_name}.module"
                mod = importlib.import_module(module_spec)
                manifest = getattr(mod, 'manifest', None) or getattr(mod, 'MANIFEST', None)
                if isinstance(manifest, ModuleManifest):
                    self.register(manifest)
                elif hasattr(mod, 'get_manifest') and callable(mod.get_manifest):
                    manifest = mod.get_manifest()
                    if isinstance(manifest, ModuleManifest):
                        self.register(manifest)
            except ImportError:
                # No module.py in this app, which is fine
                continue
            except Exception as e:
                logger.error("Error loading module manifest for app %s: %s", app_name, e)

        self._discovered = True

    def is_enabled(self, module_key: str, company_id: Optional[int] = None) -> bool:
        """
        Check if a module is enabled for a specific company or globally.
        Core module is always enabled.
        """
        if module_key == 'core':
            return True

        manifest = self.get(module_key)
        if not manifest:
            return False

        if manifest.is_core:
            return True

        if not company_id:
            # Without specific company, check if module exists
            return True

        cache_key = f"module_active_{company_id}_{module_key}"
        cached_status = cache.get(cache_key)
        if cached_status is not None:
            return cached_status

        # Query ModuleActivation model
        from core.models.module_activation import ModuleActivation
        activation = ModuleActivation.objects.filter(
            company_id=company_id,
            module_key=module_key,
        ).first()

        # By default, if no row exists, module is considered active
        is_active = activation.is_enabled if activation else True
        cache.set(cache_key, is_active, timeout=300)
        return is_active

    def set_enabled(self, module_key: str, company_id: int, is_enabled: bool, user=None) -> None:
        """Enable or disable a module for a company."""
        from core.models.module_activation import ModuleActivation
        activation, _ = ModuleActivation.objects.get_or_create(
            company_id=company_id,
            module_key=module_key,
            defaults={'is_enabled': is_enabled, 'enabled_by': user},
        )
        activation.is_enabled = is_enabled
        if user:
            activation.enabled_by = user
        activation.save(update_fields=['is_enabled', 'enabled_by', 'updated_at'])

        # Invalidate cache
        cache_key = f"module_active_{company_id}_{module_key}"
        cache.delete(cache_key)

    def validate_dependencies(self, module_key: str, company_id: Optional[int] = None) -> Tuple[bool, List[str]]:
        """
        Check if all dependencies for a module are satisfied and active.
        Returns (is_valid, list_of_missing_or_disabled_keys).
        """
        manifest = self.get(module_key)
        if not manifest:
            return False, [f"Module '{module_key}' is not registered."]

        missing_or_disabled = []
        for dep_key in manifest.dependencies:
            dep_manifest = self.get(dep_key)
            if not dep_manifest:
                missing_or_disabled.append(f"Required module '{dep_key}' is not installed.")
            elif company_id and not self.is_enabled(dep_key, company_id):
                missing_or_disabled.append(f"Required module '{dep_manifest.name}' is disabled.")

        return len(missing_or_disabled) == 0, missing_or_disabled


# Global singleton instance
module_registry = ModuleRegistry()
