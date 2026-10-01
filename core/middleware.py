"""
Core Middleware Stack
Handles Company tenancy context, Branch context, and Module enablement gating.
"""
from django.contrib import messages
from django.http import HttpResponseForbidden
from django.shortcuts import render, redirect
from django.urls import resolve
from core.registry import module_registry
from core.scoping import get_current_company, get_current_branch


class CompanyTenantMiddleware:
    """
    Attaches the active Company to the request object.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if hasattr(request, 'user') and request.user.is_authenticated:
            request.company = get_current_company(request)
        else:
            request.company = None

        response = self.get_response(request)
        return response


class BranchContextMiddleware:
    """
    Attaches the active Branch to the request object.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if hasattr(request, 'user') and request.user.is_authenticated and getattr(request, 'company', None):
            request.branch = get_current_branch(request)
        else:
            request.branch = None

        response = self.get_response(request)
        return response


class ModuleGateMiddleware:
    """
    Blocks access to URLs of disabled modules with a clear, user-friendly notice.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not hasattr(request, 'user') or not request.user.is_authenticated:
            return self.get_response(request)

        # Allow admin, static, media, logout, modules control screen
        path = request.path_info
        if (
            path.startswith('/admin/') or
            path.startswith('/static/') or
            path.startswith('/media/') or
            path.startswith('/modules/') or
            path.startswith('/login/') or
            path.startswith('/logout/')
        ):
            return self.get_response(request)

        company = getattr(request, 'company', None)
        company_id = company.id if company else None

        # Check path against registered module url_prefixes
        for manifest in module_registry.get_all():
            if manifest.is_core or not manifest.url_prefix:
                continue

            if path.startswith(manifest.url_prefix):
                if not module_registry.is_enabled(manifest.key, company_id):
                    # Check if request accepts HTML
                    if 'text/html' in request.META.get('HTTP_ACCEPT', ''):
                        return render(
                            request,
                            'core/module_disabled.html',
                            {
                                'module_name': manifest.name,
                                'module_key': manifest.key,
                                'company': company,
                            },
                            status=403,
                        )
                    return HttpResponseForbidden(f"Module '{manifest.name}' is currently disabled for this organization.")

        return self.get_response(request)
