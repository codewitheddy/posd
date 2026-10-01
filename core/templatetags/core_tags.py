"""
Core Platform Template Tags
"""
from django import template
from core.navigation import build_navigation
from core.settings_store import SettingStore

register = template.Library()


@register.simple_tag(takes_context=True)
def get_platform_navigation(context):
    """Retrieve filtered dynamic navigation menu for current user/company."""
    request = context.get('request')
    if not request:
        return []
    return build_navigation(request)


@register.simple_tag(takes_context=True)
def get_core_setting(context, module_key, key, default=''):
    """Fetch setting with hierarchical resolution."""
    request = context.get('request')
    company = getattr(request, 'company', None)
    branch = getattr(request, 'branch', None)
    return SettingStore.get(module_key, key, default=default, company=company, branch=branch)
