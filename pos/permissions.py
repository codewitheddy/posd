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
    
    return {
        'user_permissions': {
            # Role checks
            'is_admin': user.is_superuser or has_role(user, 'Administrator'),
            'is_manager': has_any_role(user, ['Administrator', 'Manager']),
            'is_stock_manager': has_any_role(user, ['Administrator', 'Manager', 'Stock Manager']),
            'is_cashier': has_any_role(user, ['Administrator', 'Manager', 'Stock Manager', 'Cashier', 'Sales Associate']),
            'is_viewer': has_any_role(user, ['Administrator', 'Manager', 'Stock Manager', 'Cashier', 'Sales Associate', 'Viewer']),
            
            # Specific permissions
            'can_manage_products': user.is_superuser or has_permission(user, 'pos.change_product'),
            'can_manage_users': user.is_superuser or has_permission(user, 'auth.change_user'),
            'can_manage_suppliers': user.is_superuser or has_permission(user, 'pos.change_supplier'),
            'can_adjust_stock': user.is_superuser or has_permission(user, 'pos.add_stockadjustment'),
            'can_view_reports': user.is_superuser or has_any_role(user, ['Administrator', 'Manager', 'Stock Manager', 'Viewer']),
            'can_manage_settings': user.is_superuser or has_permission(user, 'pos.change_businesssettings'),
            'can_view_activity_log': user.is_superuser or has_permission(user, 'pos.view_activitylog'),
            'can_manage_customers': user.is_superuser or has_permission(user, 'pos.change_customer'),
            'can_make_sales': user.is_superuser or has_permission(user, 'pos.add_sale'),
            
            # User role display
            'user_role': user.groups.first().name if user.groups.exists() else 'No Role',
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