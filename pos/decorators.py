"""
Decorators for multi-tenant views
"""

from functools import wraps
from django.shortcuts import redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required


def business_required(view_func):
    """
    Decorator to ensure business context exists in request.
    Redirects to business list if no business is set.
    """
    @wraps(view_func)
    @login_required
    def wrapper(request, *args, **kwargs):
        if not hasattr(request, 'business') or request.business is None:
            messages.error(request, 'Please select a business first.')
            return redirect('business_list')
        return view_func(request, *args, **kwargs)
    return wrapper


def business_permission_required(permission):
    """
    Decorator to check if user has specific permission in the business.
    
    Args:
        permission: Permission name (e.g., 'view', 'create', 'edit', 'delete', 'reports')
    """
    def decorator(view_func):
        @wraps(view_func)
        @business_required
        def wrapper(request, *args, **kwargs):
            # Superusers have all permissions
            if request.user.is_superuser:
                return view_func(request, *args, **kwargs)
            
            # Check business membership permission
            if hasattr(request, 'business_membership') and request.business_membership:
                if request.business_membership.has_permission(permission):
                    return view_func(request, *args, **kwargs)
            
            messages.error(request, f'You do not have permission to {permission} in this business.')
            return redirect('dashboard', slug=request.business.slug)
        return wrapper
    return decorator


def business_owner_required(view_func):
    """
    Decorator to ensure user is the business owner.
    """
    @wraps(view_func)
    @business_required
    def wrapper(request, *args, **kwargs):
        if request.user.is_superuser:
            return view_func(request, *args, **kwargs)
        
        if hasattr(request, 'business_membership') and request.business_membership:
            if request.business_membership.role == 'owner':
                return view_func(request, *args, **kwargs)
        
        messages.error(request, 'Only the business owner can perform this action.')
        return redirect('dashboard', slug=request.business.slug)
    return wrapper


def business_admin_required(view_func):
    """
    Decorator to ensure user is owner or admin.
    """
    @wraps(view_func)
    @business_required
    def wrapper(request, *args, **kwargs):
        if request.user.is_superuser:
            return view_func(request, *args, **kwargs)
        
        if hasattr(request, 'business_membership') and request.business_membership:
            if request.business_membership.role in ['owner', 'admin']:
                return view_func(request, *args, **kwargs)
        
        messages.error(request, 'Administrator access required.')
        return redirect('dashboard', slug=request.business.slug)
    return wrapper


def get_business_queryset(request, model):
    """
    Helper function to get queryset filtered by business.
    
    Args:
        request: HTTP request with business context
        model: Django model class
    
    Returns:
        Filtered queryset for the current business
    """
    if hasattr(request, 'business') and request.business:
        return model.objects.filter(business=request.business)
    return model.objects.none()
