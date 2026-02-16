"""
Context processors for multi-tenant POS system
"""

def business_context(request):
    """
    Add business context to all templates
    """
    context = {
        'has_business': hasattr(request, 'business') and request.business is not None,
    }
    
    if context['has_business']:
        context['business'] = request.business  # Add business object to context
        context['business_slug'] = request.business.slug
        
        # Add user permissions
        if hasattr(request, 'business_membership') and request.business_membership:
            membership = request.business_membership
            context['user_permissions'] = {
                'user_role': membership.get_role_display(),  # Add display name
                'role': membership.role,
                'is_owner': membership.role == 'owner',
                'is_admin': membership.role in ['owner', 'admin'],
                'is_manager': membership.role in ['owner', 'admin', 'manager'],
                'is_stock_manager': membership.role in ['owner', 'admin', 'manager', 'stock_manager'],
                'is_cashier': membership.role == 'cashier',
                'is_viewer': membership.role == 'viewer',
                'can_make_sales': membership.role in ['owner', 'admin', 'manager', 'cashier'],
                'can_manage_products': membership.role in ['owner', 'admin', 'manager', 'stock_manager'],
                'can_manage_stock': membership.role in ['owner', 'admin', 'manager', 'stock_manager'],
                'can_manage_suppliers': membership.role in ['owner', 'admin', 'manager', 'stock_manager'],
                'can_manage_purchases': membership.role in ['owner', 'admin', 'manager', 'stock_manager'],
                'can_view_reports': membership.role in ['owner', 'admin', 'manager', 'viewer'],
                'can_manage_users': membership.role in ['owner', 'admin'],
                'can_manage_settings': membership.role in ['owner', 'admin'],
                'can_view_activity_log': membership.role in ['owner', 'admin', 'manager'],
            }
        elif request.user.is_superuser:
            # Superusers have all permissions
            context['user_permissions'] = {
                'user_role': 'Superuser',  # Add display name
                'role': 'superuser',
                'is_owner': True,
                'is_admin': True,
                'is_manager': True,
                'is_stock_manager': True,
                'is_cashier': True,
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
            # No permissions
            context['user_permissions'] = {
                'user_role': 'No Access',  # Add display name
                'role': 'none',
                'is_owner': False,
                'is_admin': False,
                'is_manager': False,
                'is_stock_manager': False,
                'is_cashier': False,
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
        # No business context - no permissions
        context['user_permissions'] = {
            'user_role': 'No Access',  # Add display name
            'role': 'none',
            'is_owner': False,
            'is_admin': False,
            'is_manager': False,
            'is_stock_manager': False,
            'is_cashier': False,
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
