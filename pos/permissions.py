"""
Enhanced permission system for POS application
"""
from functools import wraps
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.shortcuts import redirect
from django.core.exceptions import PermissionDenied


def has_role(user, role_name):
    """Check if user has a specific role"""
    return user.groups.filter(name=role_name).exists()


def has_any_role(user, role_names):
    """Check if user has any of the specified roles"""
    return user.groups.filter(name__in=role_names).exists()


def has_permission(user, permission):
    """Check if user has a specific permission"""
    return user.has_perm(permission)


def role_required(*role_names):
    """Decorator to require specific roles"""
    def decorator(view_func):
        @wraps(view_func)
        @login_required
        def wrapper(request, *args, **kwargs):
            if request.user.is_superuser:
                return view_func(request, *args, **kwargs)
            
            if has_any_role(request.user, role_names):
                return view_func(request, *args, **kwargs)
            
            messages.error(request, f'Access denied. Required role: {" or ".join(role_names)}')
            return redirect('dashboard')
        return wrapper
    return decorator


def permission_required(permission, redirect_to='dashboard'):
    """Decorator to require specific permission"""
    def decorator(view_func):
        @wraps(view_func)
        @login_required
        def wrapper(request, *args, **kwargs):
            if request.user.is_superuser:
                return view_func(request, *args, **kwargs)
            
            if has_permission(request.user, permission):
                return view_func(request, *args, **kwargs)
            
            messages.error(request, f'Access denied. Required permission: {permission}')
            return redirect(redirect_to)
        return wrapper
    return decorator


def manager_or_admin_required(view_func):
    """Decorator for manager or admin access"""
    @wraps(view_func)
    @login_required
    def wrapper(request, *args, **kwargs):
        if (request.user.is_superuser or 
            has_any_role(request.user, ['Administrator', 'Manager'])):
            return view_func(request, *args, **kwargs)
        
        messages.error(request, 'Access denied. Manager or Administrator role required.')
        return redirect('dashboard')
    return wrapper


def stock_manager_required(view_func):
    """Decorator for stock management access"""
    @wraps(view_func)
    @login_required
    def wrapper(request, *args, **kwargs):
        if (request.user.is_superuser or 
            has_any_role(request.user, ['Administrator', 'Manager', 'Stock Manager'])):
            return view_func(request, *args, **kwargs)
        
        messages.error(request, 'Access denied. Stock management role required.')
        return redirect('dashboard')
    return wrapper


def cashier_or_above_required(view_func):
    """Decorator for cashier level access and above"""
    @wraps(view_func)
    @login_required
    def wrapper(request, *args, **kwargs):
        if (request.user.is_superuser or 
            has_any_role(request.user, ['Administrator', 'Manager', 'Stock Manager', 'Cashier', 'Sales Associate'])):
            return view_func(request, *args, **kwargs)
        
        messages.error(request, 'Access denied. Cashier role or higher required.')
        return redirect('dashboard')
    return wrapper


def can_manage_products(view_func):
    """Decorator for product management access"""
    @wraps(view_func)
    @login_required
    def wrapper(request, *args, **kwargs):
        if (request.user.is_superuser or 
            has_permission(request.user, 'pos.change_product') or
            has_any_role(request.user, ['Administrator', 'Manager', 'Stock Manager'])):
            return view_func(request, *args, **kwargs)
        
        messages.error(request, 'Access denied. Product management permission required.')
        return redirect('dashboard')
    return wrapper


def can_manage_users(view_func):
    """Decorator for user management access"""
    @wraps(view_func)
    @login_required
    def wrapper(request, *args, **kwargs):
        if (request.user.is_superuser or 
            has_permission(request.user, 'auth.change_user') or
            has_any_role(request.user, ['Administrator', 'Manager'])):
            return view_func(request, *args, **kwargs)
        
        messages.error(request, 'Access denied. User management permission required.')
        return redirect('dashboard')
    return wrapper


def can_view_reports(view_func):
    """Decorator for report access"""
    @wraps(view_func)
    @login_required
    def wrapper(request, *args, **kwargs):
        if (request.user.is_superuser or 
            has_any_role(request.user, ['Administrator', 'Manager', 'Stock Manager', 'Viewer'])):
            return view_func(request, *args, **kwargs)
        
        messages.error(request, 'Access denied. Report viewing permission required.')
        return redirect('dashboard')
    return wrapper


def can_manage_suppliers(view_func):
    """Decorator for supplier management access"""
    @wraps(view_func)
    @login_required
    def wrapper(request, *args, **kwargs):
        if (request.user.is_superuser or 
            has_permission(request.user, 'pos.change_supplier') or
            has_any_role(request.user, ['Administrator', 'Manager', 'Stock Manager'])):
            return view_func(request, *args, **kwargs)
        
        messages.error(request, 'Access denied. Supplier management permission required.')
        return redirect('dashboard')
    return wrapper


def can_adjust_stock(view_func):
    """Decorator for stock adjustment access"""
    @wraps(view_func)
    @login_required
    def wrapper(request, *args, **kwargs):
        if (request.user.is_superuser or 
            has_permission(request.user, 'pos.add_stockadjustment') or
            has_any_role(request.user, ['Administrator', 'Manager', 'Stock Manager'])):
            return view_func(request, *args, **kwargs)
        
        messages.error(request, 'Access denied. Stock adjustment permission required.')
        return redirect('dashboard')
    return wrapper


# Context processor for template permissions
def user_permissions(request):
    """Add user permissions to template context"""
    if not request.user.is_authenticated:
        return {}
    
    user = request.user
    
    # Check business membership role if available
    is_owner = False
    is_admin_role = False
    is_manager_role = False
    is_stock_manager_role = False
    is_cashier_role = False
    user_role_display = 'No Role'
    
    if hasattr(request, 'business_membership') and request.business_membership:
        membership = request.business_membership
        role = membership.role
        
        is_owner = role == 'owner'
        is_admin_role = role in ['owner', 'admin']
        is_manager_role = role in ['owner', 'admin', 'manager']
        is_stock_manager_role = role in ['owner', 'admin', 'manager', 'stock_manager']
        is_cashier_role = role in ['owner', 'admin', 'manager', 'stock_manager', 'cashier', 'sales']
        user_role_display = membership.get_role_display()
    else:
        # Fallback to Django groups for backward compatibility
        is_admin_role = user.is_superuser or has_role(user, 'Administrator')
        is_manager_role = has_any_role(user, ['Administrator', 'Manager'])
        is_stock_manager_role = has_any_role(user, ['Administrator', 'Manager', 'Stock Manager'])
        is_cashier_role = has_any_role(user, ['Administrator', 'Manager', 'Stock Manager', 'Cashier', 'Sales Associate'])
        user_role_display = user.groups.first().name if user.groups.exists() else 'No Role'
    
    return {
        'user_permissions': {
            # Role checks (business membership aware)
            'is_owner': is_owner,
            'is_admin': user.is_superuser or is_admin_role,
            'is_manager': is_manager_role,
            'is_stock_manager': is_stock_manager_role,
            'is_cashier': is_cashier_role,
            'is_viewer': True,  # Everyone can view
            
            # Specific permissions (owner/admin have all)
            'can_manage_products': user.is_superuser or is_owner or is_admin_role or is_manager_role or is_stock_manager_role or has_permission(user, 'pos.change_product'),
            'can_manage_users': user.is_superuser or is_owner or is_admin_role or is_manager_role or has_permission(user, 'auth.change_user'),
            'can_manage_suppliers': user.is_superuser or is_owner or is_admin_role or is_manager_role or is_stock_manager_role or has_permission(user, 'pos.change_supplier'),
            'can_adjust_stock': user.is_superuser or is_owner or is_admin_role or is_manager_role or is_stock_manager_role or has_permission(user, 'pos.add_stockadjustment'),
            'can_view_reports': user.is_superuser or is_owner or is_admin_role or is_manager_role or is_stock_manager_role or has_any_role(user, ['Viewer']),
            'can_manage_settings': user.is_superuser or is_owner or is_admin_role or is_manager_role or has_permission(user, 'pos.change_businesssettings'),
            'can_view_activity_log': user.is_superuser or is_owner or is_admin_role or is_manager_role or has_permission(user, 'pos.view_activitylog'),
            'can_manage_customers': user.is_superuser or is_owner or is_admin_role or is_manager_role or is_cashier_role or has_permission(user, 'pos.change_customer'),
            'can_make_sales': user.is_superuser or is_owner or is_admin_role or is_manager_role or is_cashier_role or has_permission(user, 'pos.add_sale'),
            'can_print_receipt': user.is_superuser or is_owner or is_admin_role or is_manager_role or is_cashier_role or (hasattr(request, 'business_membership') and request.business_membership and request.business_membership.has_permission('can_print_receipt')),
            
            # User role display
            'user_role': user_role_display,
        }
    }


# Utility functions for templates
def user_can_access(user, feature):
    """Check if user can access a specific feature"""
    feature_permissions = {
        'products': 'pos.view_product',
        'sales': 'pos.view_sale',
        'customers': 'pos.view_customer',
        'suppliers': 'pos.view_supplier',
        'reports': 'pos.view_sale',  # Basic report access
        'settings': 'pos.view_businesssettings',
        'users': 'auth.view_user',
        'stock': 'pos.view_stockadjustment',
    }
    
    if user.is_superuser:
        return True
    
    permission = feature_permissions.get(feature)
    if permission:
        return has_permission(user, permission)
    
    return False


# ============================================================================
# MULTI-BRANCH SCOPING & DRF PERMISSIONS
# ============================================================================

from rest_framework import permissions


def get_request_business(request):
    """Resolve business from request or fallback to user membership/ownership."""
    if not request:
        return None
    user = getattr(request, 'user', None)
    business = getattr(request, 'business', None) or getattr(getattr(request, '_request', None), 'business', None)

    # If user is authenticated, ensure the resolved business belongs to the user
    if user and getattr(user, 'is_authenticated', False):
        from .models import Business, BusinessMembership
        if business:
            has_access = (
                user.is_superuser or
                getattr(business, 'owner_id', None) == user.id or
                BusinessMembership.objects.filter(user=user, business=business, is_active=True).exists()
            )
            if not has_access:
                business = None

        if not business:
            bm = BusinessMembership.objects.filter(user=user, is_active=True).select_related('business').first()
            if bm:
                business = bm.business
            else:
                business = Business.objects.filter(owner=user).first() or Business.objects.filter(memberships__user=user).first()

            if business:
                try:
                    request.business = business
                    if hasattr(request, '_request') and request._request:
                        request._request.business = business
                except Exception:
                    pass
    return business


class IsHQAdminOrOwner(permissions.BasePermission):
    """DRF permission: True if user is superuser, owner, admin, or hq_admin."""
    def has_permission(self, request, view):
        if not request.user or not getattr(request.user, 'is_authenticated', False):
            return False
        if request.user.is_superuser:
            return True
        business = get_request_business(request)
        if not business:
            return True
        from .branch_services import is_owner_or_admin
        return is_owner_or_admin(request.user, business)

    def has_object_permission(self, request, view, obj):
        if not request.user or not getattr(request.user, 'is_authenticated', False):
            return False
        if request.user.is_superuser:
            return True
        business = getattr(obj, 'business', None) or get_request_business(request)
        from .branch_services import is_owner_or_admin
        return is_owner_or_admin(request.user, business)


class IsBranchManagerOrHQ(permissions.BasePermission):
    """DRF object-level permission: checks if user is manager of source/target branch or HQ admin."""
    def has_permission(self, request, view):
        return bool(request.user and getattr(request.user, 'is_authenticated', False))

    def has_object_permission(self, request, view, obj):
        if not request.user or not getattr(request.user, 'is_authenticated', False):
            return False
        if request.user.is_superuser:
            return True
        business = getattr(obj, 'business', None) or get_request_business(request)
        from .branch_services import is_owner_or_admin, is_branch_manager
        if business and is_owner_or_admin(request.user, business):
            return True

        branch = getattr(
            obj, 'branch',
            getattr(obj, 'source_branch', getattr(obj, 'requesting_branch', getattr(obj, 'destination_branch', None)))
        )
        if branch:
            return is_branch_manager(request.user, branch)
        return False


class BranchScopeMixin:
    """
    Queryset-scoping mixin for DRF ViewSets and Class-based views.
    Filters querysets by user's branch assignments unless user is HQ Admin / Owner.
    """
    branch_field = 'branch'

    def get_scoped_queryset(self, queryset):
        user = getattr(self.request, 'user', None)
        if not user or not user.is_authenticated:
            return queryset.none()
        if user.is_superuser:
            return queryset

        business = get_request_business(self.request)
        if not business:
            return queryset

        from .branch_services import is_owner_or_admin
        if is_owner_or_admin(user, business):
            return queryset

        from .models import BranchMembership
        user_branches = BranchMembership.objects.filter(
            user=user, branch__business=business, is_active=True
        ).values_list('branch_id', flat=True)

        if not user_branches:
            return queryset.none()

        field = getattr(self, 'branch_field', 'branch')
        if field == 'source_or_dest':
            from django.db.models import Q
            return queryset.filter(Q(source_branch_id__in=user_branches) | Q(destination_branch_id__in=user_branches))
        if field == 'requesting_branch':
            return queryset.filter(requesting_branch_id__in=user_branches)

        filter_kwargs = {f"{field}_id__in": user_branches}
        return queryset.filter(**filter_kwargs)