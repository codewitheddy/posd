"""
Context processors for single-store POS system with multi-branch support and Front/Back Office split
"""
from django.utils import timezone


def business_context(request):
    """
    Add store, branch, terminal, and role permissions context to all templates
    """
    business = getattr(request, 'business', None)
    has_business = business is not None
    active_branch = getattr(request, 'branch', None)

    context = {
        'has_business': has_business,
        'has_store': has_business,
        'business': business,
        'store': business,
        'business_slug': business.slug if business else 'main-store',
        'active_branch': active_branch,
        'current_branch': active_branch,
        'active_terminal': getattr(request, 'terminal', None),
        'pos_session': getattr(request, 'pos_session', None),
    }

    url_name = getattr(getattr(request, 'resolver_match', None), 'url_name', '') or ''
    path = getattr(request, 'path_info', '') or getattr(request, 'path', '') or ''
    front_office_url_names = {
        'pos_screen', 'pos_pin_login', 'terminal_pin_login', 'front_office_login', 'terminal_lock',
        'terminal_register', 'terminal_session_open', 'terminal_session_close',
        'pos_session_open', 'pos_session_close', 'front_office_pos', 'front_office_zreport',
        'complete_sale', 'held_orders_list', 'held_order_save', 'held_order_delete'
    }
    context['is_front_office'] = (
        url_name in front_office_url_names
        or path.startswith('/pos/')
        or '/pos/' in path
    )
    
    if has_business:
        from .models import Branch, BusinessSettings
        try:
            business_settings = BusinessSettings.get_settings(business)
        except Exception:
            business_settings = None
        context['business_settings'] = business_settings
        context['store_settings'] = business_settings

        try:
            branches = list(Branch.objects.filter(business=business, is_active=True).order_by('name'))
        except Exception:
            branches = []
        
        context['branches'] = branches
        context['is_multi_branch'] = len(branches) > 1

        # Compute alert count for bell badge
        try:
            from .models import Product, PurchaseItem
            from django.db import models as db_models
            today = timezone.now().date()

            low_stock_count = Product.objects.filter(
                business=business,
                is_active=True,
                stock_quantity__lte=db_models.F('low_stock_threshold'),
            ).count()

            expiring_count = PurchaseItem.objects.filter(
                business=business,
                expiry_date__isnull=False,
                expiry_date__lte=today + timezone.timedelta(days=30),
                expiry_date__gte=today,
            ).values('product').distinct().count()

            context['alert_count'] = low_stock_count + expiring_count
        except Exception:
            context['alert_count'] = 0
        
        # Add user permissions & office access
        if hasattr(request, 'business_membership') and request.business_membership:
            membership = request.business_membership
            is_owner = membership.role == 'owner'
            is_admin = membership.role in ['owner', 'admin']
            is_manager = membership.role in ['owner', 'admin', 'manager', 'chief_cashier']
            is_stock_manager = membership.role in ['owner', 'admin', 'manager', 'stock_manager']
            is_cashier = membership.role in ['cashier', 'sales']
            
            context['user_permissions'] = {
                'user_role': membership.get_role_display(),
                'role': membership.role,
                'is_owner': is_owner,
                'is_admin': is_admin,
                'is_manager': is_manager,
                'is_stock_manager': is_stock_manager,
                'is_cashier': is_cashier,
                'is_cashier_only': is_cashier and not is_manager,
                'can_access_back_office': not is_cashier or is_manager or is_admin,
                'can_access_admin': is_admin,
                'is_viewer': membership.role == 'viewer',
                'can_make_sales': is_admin or is_manager or is_cashier or membership.role == 'sales',
                'can_manage_products': is_admin or is_manager or is_stock_manager,
                'can_manage_stock': is_admin or is_manager or is_stock_manager,
                'can_manage_suppliers': is_admin or is_manager or is_stock_manager,
                'can_manage_purchases': is_admin or is_manager or is_stock_manager,
                'can_view_reports': is_admin or is_manager or membership.role == 'viewer',
                'can_manage_users': is_admin,
                'can_manage_settings': is_admin,
                'can_view_activity_log': is_admin or is_manager,
            }
        elif request.user.is_authenticated and request.user.is_superuser:
            context['user_permissions'] = {
                'user_role': 'Superuser',
                'role': 'superuser',
                'is_owner': True,
                'is_admin': True,
                'is_manager': True,
                'is_stock_manager': True,
                'is_cashier': True,
                'is_cashier_only': False,
                'can_access_back_office': True,
                'can_access_admin': True,
                'is_viewer': True,
                'can_make_sales': True,
                'can_manage_products': True,
                'can_manage_stock': True,
                'can_manage_suppliers': True,
                'can_manage_purchases': True,
                'can_view_reports': True,
                'can_manage_users': True,
                'can_manage_settings': True,
                'can_view_activity_log': True,
            }
        else:
            context['user_permissions'] = {
                'user_role': 'No Access',
                'role': 'none',
                'is_owner': False,
                'is_admin': False,
                'is_manager': False,
                'is_stock_manager': False,
                'is_cashier': False,
                'is_cashier_only': False,
                'can_access_back_office': False,
                'can_access_admin': False,
                'is_viewer': False,
                'can_make_sales': False,
                'can_manage_products': False,
                'can_manage_stock': False,
                'can_manage_suppliers': False,
                'can_manage_purchases': False,
                'can_view_reports': False,
                'can_manage_users': False,
                'can_manage_settings': False,
                'can_view_activity_log': False,
            }
    else:
        context['branches'] = []
        context['is_multi_branch'] = False
        context['user_permissions'] = {
            'user_role': 'No Access',
            'role': 'none',
            'is_owner': False,
            'is_admin': False,
            'is_manager': False,
            'is_stock_manager': False,
            'is_cashier': False,
            'is_cashier_only': False,
            'can_access_back_office': False,
            'can_access_admin': False,
            'is_viewer': False,
            'can_make_sales': False,
            'can_manage_products': False,
            'can_manage_stock': False,
            'can_manage_suppliers': False,
            'can_manage_purchases': False,
            'can_view_reports': False,
            'can_manage_users': False,
            'can_manage_settings': False,
            'can_view_activity_log': False,
        }
    
    return context
