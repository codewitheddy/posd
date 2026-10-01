"""
Dynamic Navigation Menu Builder
Aggregates menu items from all enabled modules and filters by user permissions.
"""
from typing import List
from django.urls import reverse, resolve
from django.urls.exceptions import NoReverseMatch
from core.registry import module_registry, MenuSection, MenuItem
from core.scoping import get_current_company


def user_has_menu_permission(user, permission_codename: str) -> bool:
    """Check if the user has the required permission for a menu item."""
    if not permission_codename:
        return True
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    return user.has_perm(permission_codename)


def build_navigation(request) -> List[MenuSection]:
    """
    Construct the dynamic navigation sidebar structure for the current request and user.
    """
    if not request.user.is_authenticated:
        return []

    company = get_current_company(request)
    company_id = company.id if company else None

    # Core Navigation Sections
    aggregated_sections: List[MenuSection] = []

    # Iterate through all discovered modules
    for manifest in module_registry.get_all():
        # Check if module is enabled for this company
        if not module_registry.is_enabled(manifest.key, company_id):
            continue

        for section in manifest.menu_sections:
            visible_items: List[MenuItem] = []

            for item in section.items:
                if not user_has_menu_permission(request.user, item.permission):
                    continue

                # Filter children if any
                visible_children = [
                    child for child in item.children
                    if user_has_menu_permission(request.user, child.permission)
                ]

                # Create item copy with resolved children
                item_copy = MenuItem(
                    title=item.title,
                    url_name=item.url_name,
                    icon=item.icon,
                    permission=item.permission,
                    badge=item.badge,
                    badge_class=item.badge_class,
                    order=item.order,
                    children=visible_children,
                )
                visible_items.append(item_copy)

            if visible_items:
                aggregated_sections.append(
                    MenuSection(
                        title=section.title,
                        order=section.order,
                        items=sorted(visible_items, key=lambda x: x.order),
                    )
                )

    # Sort sections by order
    return sorted(aggregated_sections, key=lambda s: s.order)
