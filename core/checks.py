"""
System Checks for Platform Core and Pluggable Modules
Enforces module integrity, dependency resolution, and circular dependency prevention.
"""
from typing import Dict, List, Set
from django.core.checks import Error, Warning, register, Tags
from core.registry import module_registry


def find_cycle(graph: Dict[str, List[str]]) -> List[str]:
    """Find and return a cycle in dependency graph if one exists."""
    visited: Set[str] = set()
    rec_stack: Set[str] = set()
    path: List[str] = []

    def dfs(node: str) -> bool:
        visited.add(node)
        rec_stack.add(node)
        path.append(node)

        for neighbor in graph.get(node, []):
            if neighbor not in visited:
                if dfs(neighbor):
                    return True
            elif neighbor in rec_stack:
                path.append(neighbor)
                return True

        path.pop()
        rec_stack.remove(node)
        return False

    for node in graph:
        if node not in visited:
            if dfs(node):
                return path

    return []


@register(Tags.compatibility)
def check_module_manifests(app_configs, **kwargs):
    """
    Validate all registered module manifests.
    Fails fast on missing dependencies or circular dependencies.
    """
    errors = []
    
    # Ensure registry autodiscovery has run
    module_registry.autodiscover()
    
    modules = module_registry.get_all()
    dep_graph: Dict[str, List[str]] = {}

    for manifest in modules:
        dep_graph[manifest.key] = manifest.dependencies

        # Check required fields
        if not manifest.key:
            errors.append(
                Error(
                    f"Module manifest '{manifest.name}' has an empty or invalid key.",
                    id='core.E001',
                )
            )

        # Check dependencies exist in registry
        for dep_key in manifest.dependencies:
            if not module_registry.get(dep_key):
                errors.append(
                    Error(
                        f"Module '{manifest.name}' ({manifest.key}) depends on '{dep_key}', which is not registered.",
                        hint=f"Ensure the app providing '{dep_key}' is in INSTALLED_APPS and defines a valid ModuleManifest.",
                        id='core.E002',
                    )
                )

    # Check for circular dependencies
    cycle = find_cycle(dep_graph)
    if cycle:
        cycle_str = ' -> '.join(cycle)
        errors.append(
            Error(
                f"Circular module dependency detected: {cycle_str}",
                hint="Refactor inter-module dependencies or use domain events instead of direct module dependency.",
                id='core.E003',
            )
        )

    return errors
