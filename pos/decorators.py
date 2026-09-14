"""
Decorators for single-store and role-based permissions
"""

from functools import wraps
from django.shortcuts import redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required


def business_required(view_func):
    """
    Decorator to ensure business/store context exists in request and user is authorized.
    """
    @wraps(view_func)
    @login_required
    def wrapper(request, *args, **kwargs):
        if not hasattr(request, 'business') or request.business is None:
            from .models import Business
            store = Business.objects.first()
            if store:
                request.business = store
                request.store = store
            else:
                messages.error(request, 'No store configuration found.')
                return redirect('login')

        # Multi-tenant boundary check: verify user belongs to this business
        if not request.user.is_superuser:
            membership = getattr(request, 'business_membership', None)
            if not membership and not getattr(request, 'test_mode_active', False):
                from .models import BusinessMembership
                membership = BusinessMembership.objects.filter(
                    user=request.user, business=request.business, is_active=True
                ).first()
                if not membership and request.user.id != getattr(request.business, 'owner_id', None):
                    messages.error(request, 'You do not have access to this business.')
                    return redirect('login')
                request.business_membership = membership

        return view_func(request, *args, **kwargs)
    return wrapper


store_required = business_required


def back_office_required(view_func):
    """
    Decorator to ensure user is permitted to access Back Office.
    Cashiers and sales-only users are strictly blocked from Back Office routes
    and redirected to Front Office POS.
    """
    @wraps(view_func)
    @business_required
    def wrapper(request, *args, **kwargs):
        if request.user.is_superuser:
            return view_func(request, *args, **kwargs)
        
        membership = getattr(request, 'business_membership', None)
        if membership:
            if membership.role in ['cashier', 'sales', 'viewer']:
                messages.error(request, 'Back Office access is restricted to Managers and Administrators.')
                return redirect('pos_screen')
            return view_func(request, *args, **kwargs)
        
        if request.user.is_staff:
            return view_func(request, *args, **kwargs)
        
        messages.error(request, 'Access restricted to Front Office POS.')
        return redirect('pos_screen')
    return wrapper


def back_office_module_required(module_name):
    """
    Enforces module-level access within Back Office:
    - 'system_admin' (Settings, Backups, User Management): Owner / Admin / Superuser only.
    - 'finances', 'hr', 'reports', 'inventory': Owner, Admin, Manager, Chief Cashier.
    """
    def decorator(view_func):
        @wraps(view_func)
        @back_office_required
        def wrapper(request, *args, **kwargs):
            if request.user.is_superuser:
                return view_func(request, *args, **kwargs)
            
            membership = getattr(request, 'business_membership', None)
            if not membership:
                messages.error(request, 'Permission denied.')
                return redirect('dashboard')
            
            role = membership.role
            if module_name == 'system_admin':
                if role not in ['owner', 'admin']:
                    messages.error(request, 'System Administrator access required.')
                    return redirect('dashboard')
            elif module_name == 'finances':
                if role not in ['owner', 'admin', 'manager', 'chief_cashier'] and not membership.has_permission('finances'):
                    messages.error(request, 'Financial management access required.')
                    return redirect('dashboard')
            elif module_name == 'hr':
                if role not in ['owner', 'admin', 'manager', 'chief_cashier'] and not membership.has_permission('hr'):
                    messages.error(request, 'HR management access required.')
                    return redirect('dashboard')
            
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator


def front_office_required(view_func):
    """
    Decorator for Front Office POS endpoints.
    Allows authenticated users (Cashiers with active PIN session, Managers, Admins).
    """
    @wraps(view_func)
    @business_required
    def wrapper(request, *args, **kwargs):
        membership = getattr(request, 'business_membership', None)
        if request.user.is_superuser or (membership and membership.is_active):
            return view_func(request, *args, **kwargs)
        messages.error(request, 'Active store membership required to access Front Office POS.')
        return redirect('login')
    return wrapper


def business_permission_required(permission):
    """
    Decorator to check if user has specific permission in the store.
    
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
            
            messages.error(request, f'You do not have permission to {permission}.')
            return redirect('dashboard')
        return wrapper
    return decorator


def business_owner_required(view_func):
    """
    Decorator to ensure user is the store owner or superuser.
    """
    @wraps(view_func)
    @business_required
    def wrapper(request, *args, **kwargs):
        if request.user.is_superuser:
            return view_func(request, *args, **kwargs)
        
        if hasattr(request, 'business_membership') and request.business_membership:
            if request.business_membership.role == 'owner':
                return view_func(request, *args, **kwargs)
        
        messages.error(request, 'Only the store owner can perform this action.')
        return redirect('dashboard')
    return wrapper


def business_admin_required(view_func):
    """
    Decorator to ensure user is owner, admin or superuser.
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
        return redirect('dashboard')
    return wrapper


def get_business_queryset(request, model):
    """
    Helper function to get queryset filtered by business/store.
    
    Args:
        request: HTTP request with business context
        model: Django model class
    
    Returns:
        Filtered queryset for the current store
    """
    if hasattr(request, 'business') and request.business:
        return model.objects.filter(business=request.business)
    return model.objects.all()


def feature_required(feature_name, upgrade_message=None):
    """
    Decorator to check if feature is enabled.
    In single-store mode, all features are enabled by default.
    """
    def decorator(view_func):
        @wraps(view_func)
        @business_required
        def wrapper(request, *args, **kwargs):
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator

